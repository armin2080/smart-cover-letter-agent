# Smart Cover Letter Agent

An intelligent Telegram bot that finds public job listings, stores them per user, and generates personalized cover letters using AI.

## Features

- 🤖 **AI-Powered Cover Letters**: Generates personalized cover letters using Groq-hosted models
- 🕷️ **Public Job Scraping**: Extracts job details from:
   - Stellenwerk.de (Dortmund student jobs)
   - StepStone public keyword pages
- 📄 **PDF Generation**: Automatically converts cover letters to professionally formatted PDFs
- 💾 **Job Tracking**: SQLite database to track viewed/unviewed job postings
- 👤 **User Profiles**: Stores user resume, expected salary, and graduation date

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd smart-cover-letter-agent
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your `config.json` file:
```json
{
   "api_key": "YOUR_GROQ_API_KEY",
   "bot_token": "YOUR_TELEGRAM_BOT_TOKEN"
}
```

### Configuration Setup

1. **Groq API Key**: Get from [Groq Console](https://console.groq.com/keys)
2. **Telegram Bot Token**: Create a bot via [@BotFather](https://t.me/botfather)
3. Optional: set `TELEGRAM_BOT_TOKEN` and `GROQ_API_KEY` as environment variables instead of using `config.json`

## Usage

### Starting the Bot

```bash
python bot.py
```

### Telegram Commands

- `/start` - Register as a new user (first-time setup)
- `/help` - Display available commands
- `/info` - View your registered information (resume, salary, graduation date)
- `/unchecked` - List unchecked jobs from Stellenwerk.de
- `/pdf` - Convert any text to PDF format
- `/scrape` - Manually trigger public job scraping from StepStone and Stellenwerk

### Quick Cover Letter Generation

Simply send a job link (from Stellenwerk, LinkedIn, or StepStone) to the bot, and it will:
1. Extract the job details
2. Generate a personalized cover letter based on your profile
3. Return a formatted PDF ready for application

## Project Structure

```
smart-cover-letter-agent/
├── agent.py          # AI cover letter generation using Groq API
├── bot.py            # Main Telegram bot with command handlers
├── scraper.py        # Web scraping for public job platforms
├── gmail.py          # Legacy Gmail monitoring helper
├── database.py       # SQLite database management
├── config.json       # Configuration file (credentials)
├── requirements.txt  # Python dependencies
└── README.md         # This file
```

## How It Works

   - Bot scrapes Stellenwerk.de public listings for Dortmund jobs
   - Stores new jobs in SQLite database
   - Bot extracts job details (title, description, requirements)

3. **Cover Letter Generation**:
   - AI analyzes job requirements vs. user's resume
   - Generates personalized, relevant cover letter
   - Returns professionally formatted PDF

## Database Schema

### Jobs Table
- `id`: Primary key
- `title`: Job title
- `link`: Job URL
- LinkedIn scraping: a Playwright fallback is available for reliable LinkedIn job discovery. If you want LinkedIn discovery to work reliably, install Playwright and the browser binaries:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

If Playwright is not installed the scraper will attempt a requests-based scrape first, but LinkedIn pages are often dynamically rendered and the Playwright path is recommended.
- `checked`: Boolean (viewed status)

### Users Table
- `id`: Primary key
- `name`: User's full name
- `username`: Telegram username
- `resume`: Full resume text
- `expected_salary`: Hourly rate in EUR
- `graduation_date`: Expected graduation date

## Security Notes

⚠️ **Important**: Never commit `config.json` to version control. Add it to `.gitignore`:
```
config.json
*.db
```

## Requirements

- Python 3.8+
- Telegram account
- Groq API access

## License

This project is for personal use. Ensure compliance with the Terms of Service of all platforms being scraped.

## Troubleshooting

**Bot not responding?**
- Verify bot token in config.json
- Check if bot.py is running without errors

**Cover letter generation fails?**
- Verify Groq API key is valid
- Check API quota limits
- Ensure job details are being extracted correctly

## Future Improvements

- [ ] Support for more job platforms
- [ ] Customizable cover letter templates
- [ ] Application tracking system
- [ ] Multi-user support
- [ ] Docker containerization
