import json
import os
import requests

config_path = os.path.join(os.path.dirname(__file__), "config.json")
with open(config_path, 'r', encoding='utf-8') as f:
    config_data = json.load(f)

# Prefer a dedicated Groq key; fall back to api_key for compatibility.
API_KEY = os.getenv('GROQ_API_KEY') or config_data.get('groq_api_key') or config_data.get('api_key', '')

url = "https://api.groq.com/openai/v1/chat/completions"
headers = {
    'Content-Type': 'application/json',
    'Authorization': f"Bearer {API_KEY}",
}

# Default Groq model; adjust if you prefer a different one.
MODEL = config_data.get('groq_model', 'llama-3.1-70b-versatile')


class Agent:
    """AI agent for generating personalized cover letters using Groq."""

    def __init__(self):
        self.instructions = (
            "Write a concise, professional cover letter tailored to the job. "
            "Use only the candidate resume and the job details provided. "
            "Do not invent facts, do not use placeholders, and return only the cover letter."
        )

    def send_request(self, job_details, resume_text):
        """Send a request to Gemini API to generate a cover letter.
        
        Args:
            job_details: Either a dict with keys 'job_title', 'job_tasks', 'job_profile',
                        or a string with job description.
        
        Returns:
            str: Generated cover letter or error message.
        """
        if not resume_text:
            return "Please register your resume first."

        prompt = self.instructions + "\n\nCandidate resume:\n" + resume_text.strip() + "\n\n"
        try:
            prompt += (
                f"Job Title: {job_details['job_title']}\n\n"
                f"Job Tasks: {job_details['job_tasks']}\n\n"
                f"Job Profile: {job_details['job_profile']}\n"
            )
        except Exception:
            prompt += str(job_details)
        prompt += "\nReturn only the cover letter."
        data = {
            "model": MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
        }
        response = requests.post(url, headers=headers, json=data).json()
        try:
            response_text = response['choices'][0]['message']['content'].strip()
        except Exception:
            response_text = response.get('error', {}).get('message', 'Unknown error').strip()
        return response_text


if __name__ == "__main__":
    # Test the agent
    agent = Agent()
    test_job = {
        'job_title': 'Data Analyst',
        'job_tasks': 'Analyze data and create reports',
        'job_profile': 'Bachelor in Computer Science, Python skills'
    }
    print(agent.send_request(test_job, "Python Django Data Science"))
