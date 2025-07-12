from bs4 import BeautifulSoup
from bs4 import NavigableString, Tag
import requests, json, re, time
from database import SQLiteDB


class Scraper:
    def __init__(self):
        pass

    def get_html(self, url):

        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        return soup
    
    def extract_stellenwerk_details(self, soup):
        job_title = soup.find('h1',class_="text-xl font-bold text-primary").text.strip()
        job_tasks = soup.find('div', class_='flex flex-col gap-4').text.strip()
        job_profile = soup.find('p', class_='flex flex-col gap-4').text.strip()

        return {
            'job_title': job_title,
            'job_tasks': job_tasks,
            'job_profile': job_profile
        }
    def send_request(self, url):
        while True:
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()  # Raise an error for bad status codes
                return response
            except requests.exceptions.RequestException as e:
                print(f"[ERROR] Exception occurred with '{url}': {str(e)}")
                time.sleep(10)
        

    def scrape_stellenwerk(self):

        # check portfolio website - irrelevant to the project. You can remove this part.:
        response = self.send_request('https://armin2080.pythonanywhere.com/')

        url = 'https://www.stellenwerk.de/dortmund?filters%5BemploymentMode%5D%5Bid%5D%5B%24in%5D%5B0%5D=8'
        url2 = 'https://www.stellenwerk.de/dortmund?pagination%5Bstart%5D=10&filters%5BemploymentMode%5D%5Bid%5D%5B%24in%5D%5B0%5D=8'
        url3 = 'https://www.stellenwerk.de/dortmund?pagination%5Bstart%5D=20&filters%5BemploymentMode%5D%5Bid%5D%5B%24in%5D%5B0%5D=8'

        urls = [url, url2, url3]
        
        db = SQLiteDB('jobs.db')

        for url in urls:
            try:
                response = self.send_request(url)
            except:
                break
            soup = BeautifulSoup(response.text, 'html.parser')

            offers_section = soup.find('section', class_='mx-auto flex w-full max-w-screen-xl flex-grow flex-col justify-between gap-4 p-4')
            offers_links = []
            for a in offers_section.find_all('a', href=True):
                link = a['href']
                if not link.startswith('http'):
                    link = 'https://www.stellenwerk.de' + link
                offers_links.append(link)
            offers_titles = offers_section.find_all('p', class_ = 'text-xl text-primary font-bold')


            for i in range(len(offers_links)):
                offer_link = offers_links[i]
                offer_title = offers_titles[i].text.strip()
                
                # Check if a row with the same link exists
                exists = db.fetchone("SELECT 1 FROM jobs WHERE link = ?", (offer_link,))
                if not exists:
                    db.execute("INSERT INTO jobs (title, link) VALUES (?,?)", (offer_title, offer_link))
            
        db.close()
        return True
    
    def extract_linkedin_details(self, link):
        
        link = link.split('?')[0]  # Remove query parameters if any
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(link, headers=headers)
        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')

        section = soup.find('div', class_='show-more-less-html__markup show-more-less-html__markup--clamp-after-5 relative overflow-hidden')

        # Convert the extracted HTML content in 'section' to plain text
        # Extract all text from the section, preserving some structure for readability    
        lines = []
        for elem in section.children:
            if isinstance(elem, NavigableString):
                text = elem.strip()
                if text:
                    lines.append(text)
            elif isinstance(elem, Tag):
                if elem.name == 'p':
                    lines.append(elem.get_text(separator=' ', strip=True))
                elif elem.name == 'ul':
                    for li in elem.find_all('li'):
                        lines.append(f"- {li.get_text(separator=' ', strip=True)}")
                elif elem.name in ['strong', 'b']:
                    lines.append(elem.get_text(separator=' ', strip=True).upper())
                else:
                    lines.append(elem.get_text(separator=' ', strip=True))
        return '\n'.join(lines)
    

    def convert_stepstone_link(self, deep_link):
        # Extract job ID from the link
        match = re.search(r'offerID/(\d+)', deep_link)
        if match:
            job_id = match.group(1)
            # Return the clean browser URL
            return f"https://www.stepstone.de/job/{job_id}"
        else:
            return "Invalid link – job ID not found."


    def extract_stepstone_details(self, link):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        }

        try:
            response = requests.get(link, headers=headers)
        except:
            response = requests.get(self.convert_stepstone_link(link), headers=headers)
            
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the JSON-LD script containing the JobPosting
        json_ld_script = soup.find('script', type='application/ld+json')
        if json_ld_script:
            job_json = json.loads(json_ld_script.string)
        else:
            # Fallback: extract JSON from the HTML using regex if not found in a <script>
            match = re.search(r'\{("@context":\s*"https://schema\.org".*?)\}\s*', response.text, re.DOTALL)
            job_json = json.loads(match.group(0)) if match else None

        if job_json:
            job_title = job_json.get('title')
            hiring_org = job_json.get('hiringOrganization', {}).get('name')
            location = job_json.get('jobLocation', {}).get('address', {}).get('addressLocality')
            
            # Get description in HTML and clean it
            job_description_html = job_json.get('description')
            
            # Clean the HTML description to plain text
            if job_description_html:
                soup_description = BeautifulSoup(job_description_html, 'html.parser')
                clean_description = soup_description.get_text(separator="\n", strip=True)

                # Further cleaning of whitespace and formatting issues
                clean_description = re.sub(r'\n+', '\n', clean_description)  # Replace multiple newlines with a single newline
                clean_description = re.sub(r'\s+', ' ', clean_description)  # Replace multiple spaces with a single space
                text = ''
                text += "Title: " +  job_title + '\n'
                text += "Company: " + hiring_org + '\n'
                text += "Location: " + location + '\n'
                text += "Description: " + clean_description + '\n'

                return text
            
        else:
            return False

    

if __name__ == "__main__":
    scraper = Scraper()

        

