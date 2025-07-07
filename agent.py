import json
import requests

with open('config.json', 'r', encoding='utf-8') as f:
    config_data = json.load(f)

API_KEY = config_data.get('api_key', '')


url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"
headers = {'Content-Type': 'application/json'}


class Agent:
    def __init__(self):
        self.prompt = """
        I want you to write a cover letter for this job offer. before writing, you must have some information about me, to personalize the cover letter. 
        My name is Armin Maddah Asl. I am a master student in data science at TU Dortmund. I have a bachelor in computer science.
        I have work experience as data analyst and also backend developer. I have C1 english and around B1 German.
        here is my resume:
        EDUCATION

ARMIN MADDAH ASL
JUNIOR DATA SCIENTIST

CONTACT
+49 177900 5396
arminmaddah.a@gmail.com
Dortmund, Germany
portfolio website

SKILLS
Python
Machine Learning
Deep Learning
Database Management
Django
Git
Linux
Power BI
Microsoft Office

TU DORTMUND
Master of Data Science 2024 - Present

KHARAZMI UNIVERSITY
Bachelor of Computer Science. GPA: 92% 2020 - 2024

LANGUAGES
English - Bilingual (C1)
German - pre-intermediate (A2 - B1)
Persian - Native

WORK EXPERIENCE

07.2022 - 01.2023 Data Analyst, Young Talents Co.

Analyzing text message data to identify trends and improve user feedback quickly.
Creating interactive Power BI dashboards connected to the company database for live data visualization.
Extracting insights from advertising and reporting systems using Python libraries.
Utilizing PostgreSQL and MySQL to analyze complex databases for accurate queries.
Visualizing data with Pandas and Matplotlib, providing clear reports on performance indicators.
02.2022 - 05.2022 Backend Developer, Arman Rayan Sharif

Developing the backend functionality of the website with Django.
Creating APIs using Django REST Framework to support frontend interactions.
Designing and implementing the admin page for efficient content management.
Working with databases to structure and store data effectively.
Contributing to the frontend, particularly in implementing the authentication system.
PROJECTS

Snake Game AI
This project implements a Snake Game where an AI learns to play the game using Deep Q-Learning. The AI trains over multiple iterations, improving its performance and strategy. The game is implemented in Python using Pygame for the visuals and PyTorch for the AI model.

Fashion MNIST Classification
This project applies Principal Component Analysis (PCA) and Random Forest Classification to the Fashion MNIST dataset. The goal is to demonstrate the effect of PCA on model performance, particularly how dimensionality reduction impacts both accuracy and training time.

Customer Behavior Analysis
This project performs customer segmentation using the RFM (Recency, Frequency, and Monetary) framework combined with K-Means clustering. The primary goal is to divide customers into distinct groups based on their purchasing behavior to enable better-targeted marketing and customer retention strategies.

CERTIFICATES

Project-Oriented Course In Creating Telegram Bot Using Python Quera | 2024
Professional Project-Oriented Course In Machine Learning With Python Quera | 2023
Task-Oriented Course In Data Analysis With Python Quera | 2023
Data Science Methodology Coursera | 2022
Tools for Data Science Coursera | 2022
Python Web Development with Django Tehran Institute of Technology | 2022
Task-Oriented course in version control with GIT Quera | 2021
Advanced Python programming and object-oriented thinking course Quera | 2021


remember, you do not need to use all the information in my resume, just use the information that is relevant to the job offer.
"""

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


if __name__ == "__main__":

    prompt = input("Enter your prompt: ")

    response = send_request(prompt)
    response_text = response['candidates'][0]['content']['parts'][0]['text'].strip()

    print(response_text)