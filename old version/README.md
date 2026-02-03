# Smart Cover Letter Agent

An intelligent Telegram bot that automates job application assistance by monitoring job postings, scraping job details, and generating personalized cover letters using AI.

## Features

- 🤖 **AI-Powered Cover Letters**: Generates personalized cover letters using Google's Gemini 2.0 Flash model
- 📧 **Email Monitoring**: Automatically monitors Gmail for job alerts from LinkedIn and StepStone
- 🕷️ **Multi-Platform Scraping**: Extracts job details from:
  - Stellenwerk.de (Dortmund student jobs)
  - LinkedIn job postings
  - StepStone job listings
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
    "api_key": "YOUR_GEMINI_API_KEY",
    "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
    "user_id": YOUR_TELEGRAM_USER_ID,
    "gmail": {
        "email": "your.email@gmail.com",
        "password": "your_app_password"
    }
}
```

### Configuration Setup

1. **Gemini API Key**: Get from [Google AI Studio](https://makersuite.google.com/app/apikey)
2. **Telegram Bot Token**: Create a bot via [@BotFather](https://t.me/botfather)
3. **Telegram User ID**: Get from [@userinfobot](https://t.me/userinfobot)
4. **Gmail App Password**: Generate from [Google Account Settings](https://myaccount.google.com/apppasswords)

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
- `/scrape` - Manually trigger job scraping from Stellenwerk.de

### Quick Cover Letter Generation

Simply send a job link (from Stellenwerk, LinkedIn, or StepStone) to the bot, and it will:
1. Extract the job details
2. Generate a personalized cover letter based on your profile
3. Return a formatted PDF ready for application

## Project Structure

```
smart-cover-letter-agent/
├── agent.py          # AI cover letter generation using Gemini API
├── bot.py            # Main Telegram bot with command handlers
├── scraper.py        # Web scraping for job platforms
├── gmail.py          # Email monitoring for job alerts
├── database.py       # SQLite database management
├── config.json       # Configuration file (credentials)
├── requirements.txt  # Python dependencies
└── README.md         # This file
```

## How It Works

1. **Job Discovery**:
   - Bot scrapes Stellenwerk.de for new job postings
   - Monitors Gmail inbox for job alerts from LinkedIn/StepStone
   - Stores new jobs in SQLite database

2. **User Interaction**:
   - User sends job link to bot
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
- Google Gemini API access
- Gmail account with app password enabled

## License

This project is for personal use. Ensure compliance with the Terms of Service of all platforms being scraped.

## Troubleshooting

**Bot not responding?**
- Verify bot token in config.json
- Check if bot.py is running without errors

**Gmail monitoring not working?**
- Ensure app password is correctly set (not regular password)
- Enable IMAP in Gmail settings
- Check if 2FA is enabled on Gmail account

**Cover letter generation fails?**
- Verify Gemini API key is valid
- Check API quota limits
- Ensure job details are being extracted correctly

## Future Improvements

- [ ] Add OAuth2 for Gmail authentication
- [ ] Support for more job platforms
- [ ] Customizable cover letter templates
- [ ] Application tracking system
- [ ] Multi-user support
- [ ] Docker containerization
