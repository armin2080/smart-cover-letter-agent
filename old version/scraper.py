from bs4 import BeautifulSoup
from bs4 import NavigableString, Tag
import requests, json, re, time
from database import SQLiteDB
from relevance import job_matches_resume, extract_resume_search_terms
import requests.utils


class Scraper:
    """Web scraper for extracting job details from multiple job platforms."""
    
    def __init__(self):
        pass

    def get_html(self, url):
        """Fetch and parse HTML content from a URL.
        
        Args:
            url: The URL to fetch.
            
        Returns:
            BeautifulSoup: Parsed HTML content.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        return soup
    
    def extract_stellenwerk_details(self, soup):
        """Extract job details from Stellenwerk HTML.
        
        Args:
            soup: BeautifulSoup object containing the parsed HTML.
            
        Returns:
            dict: Job details with keys 'job_title', 'job_tasks', 'job_profile'.
        """
        job_title_elem = soup.find('h1',class_="text-xl font-bold text-primary")
        job_tasks_elem = soup.find('div', class_='flex flex-col gap-4')
        job_profile_elem = soup.find('p', class_='flex flex-col gap-4')

        job_title = job_title_elem.text.strip() if job_title_elem else "N/A"
        job_tasks = job_tasks_elem.text.strip() if job_tasks_elem else "N/A"
        job_profile = job_profile_elem.text.strip() if job_profile_elem else "N/A"

        return {
            'job_title': job_title,
            'job_tasks': job_tasks,
            'job_profile': job_profile
        }
    def send_request(self, url, max_retries=3):
        retries = 0
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        while retries < max_retries:
            try:
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()  # Raise an error for bad status codes
                return response
            except requests.exceptions.RequestException as e:
                retries += 1
                print(f"[ERROR] Exception occurred with '{url}': {str(e)} (Attempt {retries}/{max_retries})")
                if retries < max_retries:
                    time.sleep(10)
        print(f"[ERROR] Max retries reached for '{url}'. Giving up.")
        return None
        

    def scrape_stellenwerk(self, user_id, resume_text):
        """Scrape job listings from Stellenwerk Dortmund.
        
        Returns:
            bool: True if scraping was successful, False otherwise.
        """
        url = 'https://www.stellenwerk.de/dortmund'
        url2 = 'https://www.stellenwerk.de/dortmund?pagination%5Bstart%5D=10'
        url3 = 'https://www.stellenwerk.de/dortmund?pagination%5Bstart%5D=20'

        urls = [url, url2, url3]
        
        db = SQLiteDB('jobs.db')

        for url in urls:
            try:
                response = self.send_request(url)
                if response is None:
                    break
            except:
                break
            soup = BeautifulSoup(response.text, 'html.parser')

            offers_section = soup.find('section', class_='mx-auto flex w-full max-w-screen-xl flex-grow flex-col justify-between gap-4 p-4')
            if not offers_section:
                print(f"[WARNING] Stellenwerk offers section not found for {url}")
                continue
            offers = {}
            for a in offers_section.find_all('a', href=True):
                href = a['href']
                if not href.startswith('/dortmund/'):
                    continue
                if not re.search(r'-\d+-\d+$', href):
                    continue
                link = f"https://www.stellenwerk.de{href}"
                title = a.get_text(" ", strip=True)
                if not title:
                    slug = href.rsplit('/', 1)[-1]
                    title = slug.rsplit('-', 2)[0].replace('-', ' ')
                offers[link] = title

            if not offers:
                print(f"[WARNING] No offers found for {url}")
                continue
            for offer_link, offer_title in offers.items():
                
                if not job_matches_resume(offer_title, resume_text):
                    continue

                # Check if a row with the same link exists
                exists = db.fetchone("SELECT 1 FROM jobs WHERE link = ? AND user_id = ?", (offer_link, user_id))
                if not exists:
                    db.execute("INSERT INTO jobs (title, link, user_id) VALUES (?,?,?)", (offer_title, offer_link, user_id))
            
        db.close()
        return True

    def scrape_stepstone(self, user_id, resume_text):
        """Scrape StepStone public keyword pages derived from the user's resume."""
        search_terms = extract_resume_search_terms(resume_text)
        if not search_terms:
            print("[WARNING] No resume search terms found for StepStone scraping.")
            return False

        db = SQLiteDB('jobs.db')
        found_any = False

        for term in search_terms:
            term_slug = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")
            if not term_slug:
                continue

            urls = [
                f"https://www.stepstone.de/jobs/{term_slug}",
                f"https://www.stepstone.de/jobs/{term_slug}?page=2",
            ]

            for url in urls:
                response = self.send_request(url)
                if response is None:
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')
                offers = {}

                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if 'stellenangebote--' not in href or '-inline.html' not in href:
                        continue
                    if href.startswith('/'):
                        link = f"https://www.stepstone.de{href}"
                    elif href.startswith('http'):
                        link = href
                    else:
                        continue

                    title = a.get_text(' ', strip=True)
                    if not title:
                        continue
                    offers[link] = title

                if not offers:
                    print(f"[WARNING] No StepStone offers found for {url}")
                    continue

                found_any = True
                for offer_link, offer_title in offers.items():
                    if not job_matches_resume(offer_title, resume_text):
                        continue

                    exists = db.fetchone("SELECT 1 FROM jobs WHERE link = ? AND user_id = ?", (offer_link, user_id))
                    if not exists:
                        db.execute("INSERT INTO jobs (title, link, user_id) VALUES (?,?,?)", (offer_title, offer_link, user_id))

        db.close()
        return found_any
    
    def extract_linkedin_details(self, link):
        """Extract job details from LinkedIn job posting.
        
        Args:
            link: LinkedIn job URL.
            
        Returns:
            str: Extracted job description as plain text.
        """
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


    def scrape_linkedin(self, user_id, resume_text):
        """Discover LinkedIn jobs using resume-driven keywords.

        Tries a simple requests-based scrape first; if the page is dynamically
        rendered or requests returns no results, falls back to Playwright
        when available for a reliable render.
        """
        search_terms = extract_resume_search_terms(resume_text)
        if not search_terms:
            print("[WARNING] No resume search terms found for LinkedIn scraping.")
            return False

        db = SQLiteDB('jobs.db')
        found_any = False

        for term in search_terms:
            query = requests.utils.quote(term)
            url = f"https://www.linkedin.com/jobs/search?keywords={query}"

            # Try fast requests-based fetch first
            try:
                resp = self.send_request(url)
                if resp:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    links = []
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if 'linkedin.com/jobs/view' in href or 'linkedin.com/jobs/' in href:
                            if href.startswith('/'):
                                link = f"https://www.linkedin.com{href}"
                            else:
                                link = href
                            title = a.get_text(' ', strip=True)
                            if title:
                                links.append((link, title))

                    if links:
                        found_any = True
                        for offer_link, offer_title in links:
                            if not job_matches_resume(offer_title, resume_text):
                                continue
                            exists = db.fetchone("SELECT 1 FROM jobs WHERE link = ? AND user_id = ?", (offer_link, user_id))
                            if not exists:
                                db.execute("INSERT INTO jobs (title, link, user_id) VALUES (?,?,?)", (offer_title, offer_link, user_id))
                        continue
            except Exception as exc:
                print(f"[DEBUG] requests LinkedIn fetch failed for {url}: {exc}")

            # Fallback to Playwright for reliable rendering
            try:
                ok = self.scrape_linkedin_playwright(term, db, user_id, resume_text)
                if ok:
                    found_any = True
            except Exception as exc:
                print(f"[WARNING] Playwright LinkedIn scrape failed for '{term}': {exc}")

        db.close()
        return found_any

    def scrape_linkedin_playwright(self, term, db: SQLiteDB, user_id: str, resume_text: str):
        """Use Playwright to render LinkedIn search pages and extract job links.

        This function requires `playwright` to be installed and the browser
        binaries to be set up (`playwright install`). If not available, it
        raises ImportError which the caller will catch.
        """
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise ImportError("Playwright not installed or not available: " + str(exc))

        query = requests.utils.quote(term)
        search_url = f"https://www.linkedin.com/jobs/search?keywords={query}"

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"]) 
            page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            page.goto(search_url, timeout=30000)
            # wait a bit for dynamic content
            page.wait_for_timeout(2500)
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')

            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if 'linkedin.com/jobs/view' in href or 'linkedin.com/jobs/' in href:
                    if href.startswith('/'):
                        link = f"https://www.linkedin.com{href}"
                    else:
                        link = href
                    title = a.get_text(' ', strip=True)
                    if title:
                        links.append((link, title))

            if not links:
                browser.close()
                return False

            for offer_link, offer_title in links:
                if not job_matches_resume(offer_title, resume_text):
                    continue
                exists = db.fetchone("SELECT 1 FROM jobs WHERE link = ? AND user_id = ?", (offer_link, user_id))
                if not exists:
                    db.execute("INSERT INTO jobs (title, link, user_id) VALUES (?,?,?)", (offer_title, offer_link, user_id))

            browser.close()
            return True
    

    def convert_stepstone_link(self, deep_link):
        # Extract job ID from common StepStone URL patterns
        match = re.search(r'jobs----(\d+)-inline', deep_link)
        if not match:
            match = re.search(r'job/(\d+)', deep_link)
        if not match:
            match = re.search(r'offerID/(\d+)', deep_link)
        if match:
            job_id = match.group(1)
            return f"https://www.stepstone.de/job/{job_id}"
        return "Invalid link – job ID not found."


    def extract_stepstone_details(self, link):
        """Extract job details from StepStone job posting.
        
        Args:
            link: StepStone job URL.
            
        Returns:
            str: Formatted job details or False if extraction fails.
        """
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
    # Test the scraper
    scraper = Scraper()
    result = scraper.scrape_stellenwerk("test-user", "Python Django Data Science")
    print(f"Scraping completed: {result}")
