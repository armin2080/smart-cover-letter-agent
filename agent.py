import json
import requests

with open('config.json', 'r', encoding='utf-8') as f:
    config_data = json.load(f)

API_KEY = config_data.get('api_key', '')


url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"
headers = {'Content-Type': 'application/json'}

resume = config_data.get('resume', '')

class Agent:
    def __init__(self):
        self.prompt = """
        I want you to write a cover letter for this job offer. before writing, you must have some information about me, to personalize the cover letter. 
        My name is Armin Maddah Asl. I am a master student in data science at TU Dortmund. I have a bachelor in computer science.
        I have work experience as data analyst and also backend developer. I have C1 english and around B1 German.
        here is my resume:
        """
        self.prompt += resume + "\n\n"
        self.prompt += "remember, you do not need to use all the information in my resume, just use the information that is relevant to the job offer."


    def send_request(self, job_details):
        try:
            self.prompt += f"Job Title: {job_details['job_title']}\n\nJob Tasks: {job_details['job_tasks']}\n\nJob Profile: {job_details['job_profile']}."
        except:
            self.prompt += job_details
        self.prompt += "remember, just send me the cover letter, nothing else, no explanation, no introduction, just the cover letter. do not use any placeholders in your letter. again I mention 'DON'T USE PLACEHOLDERS'. also, you do not need to mention where you read the job, just write the letter."
        data = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": self.prompt
                        }
                    ]
                }
            ]
        }
        response = requests.post(url, headers=headers, json=data).json()
        try:
            response_text = response['candidates'][0]['content']['parts'][0]['text'].strip()
        except:
            response_text = response['error']['message'].strip()
        return response_text
