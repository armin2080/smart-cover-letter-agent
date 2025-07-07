from email.header import decode_header
import json, re, requests, email, imaplib, time
from database import JobDatabase

# Gmail IMAP settings
with open('config.json', 'r') as f:
    config = json.load(f)

EMAIL_ACCOUNT = config['gmail']['email']
PASSWORD = config['gmail']['password']

email_list = ['express@jobagent.stepstone.de', 'info@jobagent.stepstone.de',]


class GmailClient:
    def __init__(self,EMAIL_ACCOUNT, PASSWORD, email_list=email_list):
        self.IMAP_SERVER = "imap.gmail.com" 
        self.EMAIL_ACCOUNT = EMAIL_ACCOUNT
        self.PASSWORD = PASSWORD
        self.mail = imaplib.IMAP4_SSL(self.IMAP_SERVER)
        self.email_list = email_list
    def get_email_body(self, msg):
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    charset = part.get_content_charset() or "utf-8"
                    return part.get_payload(decode=True).decode(charset, errors="replace")
        else:
            charset = msg.get_content_charset() or "utf-8"
            return msg.get_payload(decode=True).decode(charset, errors="replace")
        return ""
    

    def get_unread_emails(self):
        self.mail.login(self.EMAIL_ACCOUNT, self.PASSWORD)
        self.mail.select("inbox")
        
        # Search for unread emails
        status, messages = self.mail.search(None, 'UNSEEN')
        
        # Convert messages to a list of email IDs
        email_ids = messages[0].split()
        
        unread_emails = []
        
        for e_id in email_ids:
            # Fetch the email by ID without setting it as read (use BODY.PEEK)
            res, msg = self.mail.fetch(e_id, '(BODY.PEEK[])')
            msg = msg[0][1]
            
            # Parse the email content
            msg = email.message_from_bytes(msg)
            subject, encoding = decode_header(msg['Subject'])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding if encoding else 'utf-8')
            
            from_ = msg.get('From')

            # Get the email body
            body = self.get_email_body(msg)

            
            unread_emails.append({
            'id': e_id,
            'subject': subject,
            'from': from_,
            'body': body,
            })
        
        
        return unread_emails
    
    def filter_unread_emails(self):
        unread_emails = self.get_unread_emails()
        filtered_emails = {email_addr: [] for email_addr in self.email_list}
        for email_data in unread_emails:
            for sender in email_list:
                if sender in email_data['from']:
                    filtered_emails[sender].append(email_data)
        return filtered_emails
    
    def convert_stepstone_link(self, deep_link):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"  # helps avoid blocks
        }
        penalty = 5
        while True:
                

            try:
                # Follow redirects to get the final destination link
                response = requests.get(deep_link, allow_redirects=True, headers=headers, timeout=10)

                if response.status_code == 200:
                    link = response.url.split('application')[0]
                    if 'jobs----' in link:
                        link, job_id = link.split('-inline')[0].split('s----')
                    
                        return link + '/' + job_id + '/'
                    
                    return link

                else:
                    print(f"[ERROR] Failed to resolve link '{deep_link}'. HTTP {response.status_code}")

            except requests.exceptions.RequestException as e:
                print(f"[ERROR] Exception occurred with '{deep_link}': {str(e)}")
            finally:
                print(f"[INFO] Retrying to resolve link '{deep_link}' after {penalty} seconds...")
                time.sleep(penalty)
                penalty *= 2
        

    def extract_job_details(self):
        jobs = self.filter_unread_emails()
        job_details = []
        for email_addr, emails in jobs.items():
            # extract details by parsing the email body
            for email in emails:
                subject = email['subject']
                e_id = email['id']
                # stepstone recommendation:

                # stepstone new job opportunityies for you:
                if ('are looking for candidates' in subject) or ('New job opportunities for you' in subject):
                    body = email['body']
                    jobs = body.split('Perfect\xa0Match\xa0\xa0\nThis job suits you beautifully. Your CV fits perfectly.')[1:]
                    for job in jobs:
                        lines = job.strip().split('\n')
                        if lines:
                            title = lines[0].strip()
                            # Try to find the first link in the job section
                            match = re.search(r'(https?://[^\s\'"]+)', job)
                            final_link = match.group(0) if match else None
                            final_link = self.convert_stepstone_link(final_link) if final_link else None
                            if final_link:
                                self.mail.store(e_id, '+FLAGS', '\\Seen')

                        job_details.append({
                        'title': title,
                        'link': final_link,
                        'from': email_addr,
                        'subject': subject,
                        })
                    if len(job_details) > 0:
                        continue
                    
                
                
                else:
                    if "Get it while it's hot" in subject:  
                        title = subject.split('hot:')[1]
                    
                    elif 'Armin, our recommendation:' in subject:
                        title = subject.split('Armin, our recommendation: ')[-1].strip()
                    
                    elif "You have good chance:" in subject:
                        title = subject.split('You have good chance: ')[-1].strip()
                    
                    elif 'Start your application today:' in subject:
                        title = subject.split('Start your application today: ')[-1].strip()
                    
                    elif 'You have the skills for this job:' in subject:
                        title = subject.split('You have the skills for this job: ')[-1].strip()
                    
                    elif "You're wanted:" in subject:
                        title = subject.split("You're wanted: ")[-1].strip()
                    else:
                        title = subject.split(': ')[-1].strip()
    
                    
                    body = email['body']
                    match = re.search(r'(https?://)?(click\.stepstone\.de[^\s\'"]+)', body)
                    if match:
                        # Ensure the link has the protocol
                        link = match.group(0)
                        if not link.startswith('http'):
                            link = 'https://' + link
                    else:
                        link = None

                    if link:
                        final_link = self.convert_stepstone_link(link)
                        if final_link:
                            self.mail.store(e_id, '+FLAGS', '\\Seen')

                
                job_details.append({
                    'title': title,
                    'link': final_link,
                    'from': email_addr,
                    'subject': subject,
                })


                
        if job_details:
            db = JobDatabase('jobs.db')
            for job in job_details:
                if not db.job_exists(job['link']):
                    db.add_job(job['title'], job['link'])
            db.close()
        self.mail.logout()
        
        return True

                    

    
if __name__ == "__main__":
    agent = GmailClient(EMAIL_ACCOUNT, PASSWORD, email_list)
    agent.extract_job_details()