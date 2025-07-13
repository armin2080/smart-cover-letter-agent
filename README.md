
# Smart Cover Letter Agent

This project scrapes job listings daily from platforms like **Stellenwerk** and monitors emails from **LinkedIn** and **StepStone** to collect relevant job offers. It analyzes each job description alongside your personal resume and uses a language model to automatically generate tailored cover letters. Integrated with Telegram for easy interaction, it streamlines the entire job application process.

## Features

- **Automated Job Scraping:** The agent scrapes job listings daily from stellenwerk.de and retrieves relevant emails from LinkedIn and StepStone.
- **Telegram Bot Integration:** Users receive daily notifications of new job listings directly in their Telegram bot.
- **AI-Powered Cover Letters:** The agent generates personalized cover letters by analyzing the job description and matching it with the user's resume.
- **PDF Generation:** A clean PDF file of the generated cover letter is created and sent to the user.
- **Dataset Management:** All scraped job offers are stored in a structured dataset for easy access and review.
- **Future Scalability:** Plans to expand scraping capabilities to additional job offer websites such as Indeed.



## Tech Stack

- **Programming Language:**
  - Python

- **Web Scraping:**
  - Beautiful Soup 4

- **Email Handling:**
  - IMAP library

- **Database Management:**
  - SQLite3

- **Telegram Bot Integration:**
  - python-telegram-bot

- **PDF Generation:**
  - ReportLab


## Installation

## Installation Instructions

To set up the Smart Cover Letter Agent on your local machine, follow these steps:

1. **Clone the Repository:**
   ```bash
   git clone git@github.com:armin2080/smart-cover-letter-agent.git
   cd smart-cover-letter-agent
   ```

2. **Create a Virtual Environment** (optional but recommended):
   ```python
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install Required Packages:** Make sure you have pip installed, then run.
   ```bash
   pip install -r requirements.txt
   ```

4. **Create Configuration File:** Create a config.json file in the project root with the following structure.
   ```json
   {
    "api_key": "YOUR_AGENT_API_KEY",
    "bot_token": "YOUR_BOT_TOKEN",
    "user_id": "YOUR_TELEGRAM_USER_ID",
    "gmail": {
        "email": "YOUR_EMAIL",
        "password": "YOUR_APP_PASSWORD"
    },
    "resume": "YOUR_RESUME_IN_TEXT_FORMAT"
   }
    ```


## Usage

Once you have installed the Smart Cover Letter Agent and set up your configuration file, you can start using it as follows:

1. **Run the Application:**
Make sure your virtual environment is activated (if applicable) and run:
   ```bash
   python bot.py
   ```

2. **Interact with the Telegram Bot:** 
Using your Telegram bot commands, you can access various features of the agent. Here are the available commands:

- `/start` - Start the bot and register your information.
- `/info` - Get your registered information (resume, expected salary, graduation date).
- `/unchecked` - Get a list of unchecked jobs in stellenwerk.de in Dortmund.
- `/pdf` - Convert text to PDF.
- `/scrape` - Manually trigger a job scraping from stellenwerk.de.

3. **Request a Cover Letter:**
You can also send a message with a job link (from Stellenwerk, LinkedIn, or StepStone) to get a personalized cover letter.

4. **Receive Your Cover Letter:** 
After processing your request, you will receive a clean PDF file of the generated cover letter directly in your Telegram chat.


## Contributing

Contributions to the Smart Cover Letter Agent are welcome! If you would like to contribute, please follow these guidelines:

1. **Fork the Repository:**
   - Click on the "Fork" button at the top right of this page to create your own copy of the repository.

2. **Create a Branch:**
   - Create a new branch for your feature or bug fix:
     ```bash
     git checkout -b feature/YourFeatureName
     ```

3. **Make Your Changes:**
   - Make your changes and commit them with a descriptive message:
     ```bash
     git commit -m "Add new feature"
     ```

4. **Push to Your Fork:**
   - Push your changes back to your forked repository:
     ```bash
     git push origin feature/YourFeatureName
     ```

5. **Open a Pull Request:**
   - Go to the original repository and click on "New Pull Request." Describe your changes and submit it for review.

6. **Respect Project Guidelines:**
   - Please ensure that your code follows existing project conventions and is well-documented.
## License

This project is licensed under the **MIT** License - see the [LICENSE](https://choosealicense.com/licenses/mit/) file for details.

