import json, os, logging, datetime, re, io, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler
from scraper import Scraper 
from database import JobDatabase, UserDatabase
from agent import Agent 
from gmail import GmailClient
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.pagesizes import letter


# Load configuration from config.json
config_path = os.path.join(os.path.dirname(__file__), "config.json")
with open(config_path, "r") as config_file:
    config = json.load(config_file)

# --- CONFIGURATION ---
BOT_TOKEN = config['bot_token']
USER_CHAT_ID = config['user_id']

# --- SCRAPER AND DATABASE SETUP ---
scraper = Scraper()
job_db = JobDatabase("jobs.db")
user_db = UserDatabase("users.db")
agent = Agent()

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Define conversation states
PDF_TEXT = range(1)
RESUME_TEXT, EXPECTED_SALARY, GRADUATION_DATE = range(1,4)


# --- STARTUP MESSAGE ---
# --- USER REGISTRATION CONVERSATION HANDLER ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  username = update.effective_user.username
  user = user_db.get_user(username)
  if user:
    await update.message.reply_text(
      f"Hello {update.effective_user.first_name}, I am your job scraping bot! Use /help to see available commands."
    )
    return ConversationHandler.END
  else:
    await update.message.reply_text(f"Hello @{username}!\n\nIt seems like you are a new user. I need some information from you before you can use the bot.")
    time.sleep(5)  # Wait for 5 second to ensure the message is sent before the next one
    await update.message.reply_text(
      f"""
First, please send me your resume in text format. Here is an example of what I need:

[YOUR NAME]
[YOUR JOB TITLE]

CONTACT
[PHONE NUMBER]
[EMAIL ADDRESS]
[LOCATION]
[PORTFOLIO LINK]

SKILLS
- [SKILL 1]
- [SKILL 2]
- [SKILL 3]

EDUCATION
[UNIVERSITY NAME] - [DEGREE TITLE] [YEAR STARTED - YEAR GRADUATED]

LANGUAGES
- [LANGUAGE 1 - PROFICIENCY LEVEL]
- [LANGUAGE 2 - PROFICIENCY LEVEL]

WORK EXPERIENCE
[START DATE - END DATE] [JOB TITLE], [COMPANY NAME]
- [RESPONSIBILITY/INFO]

PROJECTS
[PROJECT NAME]
[DESCRIPTION/INFO]

CERTIFICATES
[CERTIFICATE NAME] | [YEAR OBTAINED]
      """    
    )
    context.user_data['registration_step'] = 'resume'
    return RESUME_TEXT

async def get_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
  resume_text = update.message.text
  if not resume_text or len(resume_text) < 20:
    await update.message.reply_text("Please send a valid resume text (at least 20 characters).")
    return RESUME_TEXT
  context.user_data['resume'] = resume_text
  await update.message.reply_text("What is your expected salary per hour (in EUR)?")
  return EXPECTED_SALARY

async def get_expected_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
  salary_text = update.message.text
  try:
    salary = int(salary_text.replace(",", "").replace(".", ""))
    if salary <= 0:
      raise ValueError("Salary must be a positive number.")
  except Exception:
    await update.message.reply_text("Please enter a valid number for your expected salary (e.g. 15).")
    return EXPECTED_SALARY
  context.user_data['expected_salary'] = salary
  await update.message.reply_text("What is your graduation date? (Format: YYYY.MM.DD)")
  return GRADUATION_DATE

async def get_graduation_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
  date_text = update.message.text
  try:
    grad_date = datetime.datetime.strptime(date_text, "%Y.%m.%d").date()
  except Exception:
    await update.message.reply_text("Please enter the date in the format YYYY.MM.DD (e.g. 2026-07-01).")
    return GRADUATION_DATE
  context.user_data['graduation_date'] = str(grad_date)
  username = update.effective_user.username

  name = update.effective_user.first_name + " " + update.effective_user.last_name if update.effective_user.last_name else update.effective_user.first_name
  user_db.add_user(
    name=name,
    username=username,
    resume=context.user_data['resume'],
    expected_salary=context.user_data['expected_salary'],
    graduation_date=context.user_data['graduation_date']
  )
  await update.message.reply_text("Thank you! Your data has been saved. You can now use the bot. Use /help to see available commands.")
  return ConversationHandler.END


# --- /info COMMAND HANDLER ---
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username
    user = user_db.get_user(username)
    
    if not user:
        await update.message.reply_text("You are not registered yet. Please use /start to register first.")
        return

    info_text = (
        f"Resume:\n {user[3]}\n\n\n\n\n"
        f"Expected Salary: {user[4]} EUR/hour\n\n"
        f"Graduation Date: {user[5]}"
    )
    await update.message.reply_text(info_text)


# --- HELP COMMAND HANDLER ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Here are the available commands:\n"
        "/start - Start the bot and register your information.\n"
        "/info - Get your registered information (resume, expected salary, graduation date).\n"
        "/unchecked - Get a list of unchecked jobs in stellenwerk.de in Dortmund.\n"
        "/pdf - Convert text to PDF.\n"
        "/scrape - Manually trigger a job scraping from stellenwerk.de.\n"
        "You can also send a message with a job link (from Stellenwerk, Linkedin, or StepStone) to get a cover letter."
    )
    await update.message.reply_text(help_text)

# --- SCRAPE JOB FUNCTION ---
async def scrape_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scrape = scraper.scrape_stellenwerk()
    email_checker = GmailClient(config['gmail']['email'], config['gmail']['password'])
    email_checker.extract_job_details()
    if scrape:
        await context.bot.send_message(chat_id=USER_CHAT_ID, text="✅ Scraping completed.")
    else:
        await context.bot.send_message(chat_id=USER_CHAT_ID, text="❌ Scraping failed.")

# --- /unchecked COMMAND HANDLER ---
async def unchecked_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = job_db.get_unchecked_jobs()

    if not jobs:
        await update.message.reply_text("No unchecked jobs found.")
        return

    keyboard = [
        [InlineKeyboardButton(job[1], callback_data=job[0])]
        for job in jobs
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select a job to get the link:", reply_markup=reply_markup)

# --- CALLBACK FOR BUTTON PRESS ---
async def job_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    job_id = query.data
    job = job_db.get_job_by_id(job_id)
    job_db.mark_job_as_checked(job_id)

    await query.edit_message_text(text=f"Here is the job link:\n{job[2]}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
  message_text = update.message.text
  url_pattern = re.compile(r'https?://\S+')
  match = url_pattern.search(message_text)
  
  if not match:
    await update.message.reply_text(f"No links found in the message.")

  else:

    if 'stellenwerk.de' in match.group(0):
      soup = scraper.get_html(match.group(0))
      job_details = scraper.extract_stellenwerk_details(soup)

    elif 'linkedin.com' in match.group(0):
      job_details = scraper.extract_linkedin_details(match.group(0))

    elif 'stepstone.de' or 'offerView' in match.group(0):
      job_details = scraper.extract_stepstone_details(match.group(0))
    
    message = agent.send_request(job_details)

    if message == 'The model is overloaded. Please try again later.':
      await update.message.reply_text("The model is overloaded. Please try again later.")

    else:
       # Create a PDF buffer
      pdf_buffer = io.BytesIO()
      c = canvas.Canvas(pdf_buffer, pagesize=letter)
      width, height = letter
      left_margin = 50
      right_margin = 50
      top_margin = 50
      bottom_margin = 50
      usable_width = width - left_margin - right_margin
      y = height - top_margin

      # Split message into paragraphs and lines
      paragraphs = message.split('\n')
      line_height = 14
      font_name = "Times-Roman"
      font_size = 12
      c.setFont(font_name, font_size)

      for para in paragraphs:
        if not para.strip():
          y -= line_height  # Empty line for paragraph break
          continue
        words = para.split()
        line = ""
        for word in words:
          test_line = f"{line} {word}".strip()
          if stringWidth(test_line, font_name, font_size) <= usable_width:
            line = test_line
          else:
            c.drawString(left_margin, y, line)
            y -= line_height
            line = word
            if y < bottom_margin:
              c.showPage()
              c.setFont(font_name, font_size)
              y = height - top_margin
        if line:
          c.drawString(left_margin, y, line)
          y -= line_height
        y -= line_height  # Extra line for paragraph break

      c.save()
      pdf_buffer.seek(0)
      # Generate a unique filename using timestamp
      timestamp = datetime.datetime.now().strftime("%m_%d_%H:%M")
      filename = f"cover_letter_{timestamp}.pdf"
      await update.message.reply_document(document=InputFile(pdf_buffer, filename=filename))


async def pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("Please send the text you want to convert to PDF.")
  return PDF_TEXT

async def convert_to_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
  message_text = update.message.text
  if not message_text:
    await update.message.reply_text("No text to convert to PDF.")
    return ConversationHandler.END

  # Create a PDF buffer
  pdf_buffer = io.BytesIO()
  c = canvas.Canvas(pdf_buffer, pagesize=letter)
  width, height = letter
  left_margin = 50
  right_margin = 50
  top_margin = 50
  bottom_margin = 50
  usable_width = width - left_margin - right_margin
  y = height - top_margin

  # Split message into paragraphs and lines
  paragraphs = message_text.split('\n')
  line_height = 14
  font_name = "Times-Roman"
  font_size = 12
  c.setFont(font_name, font_size)

  for para in paragraphs:
    if not para.strip():
      y -= line_height  # Empty line for paragraph break
      continue
    words = para.split()
    line = ""
    for word in words:
      test_line = f"{line} {word}".strip()
      if stringWidth(test_line, font_name, font_size) <= usable_width:
        line = test_line
      else:
        c.drawString(left_margin, y, line)
        y -= line_height
        line = word
        if y < bottom_margin:
          c.showPage()
          c.setFont(font_name, font_size)
          y = height - top_margin
    if line:
      c.drawString(left_margin, y, line)
      y -= line_height
    y -= line_height  # Extra line for paragraph break

  c.save()
  pdf_buffer.seek(0)
  
  timestamp = datetime.datetime.now().strftime("%m_%d_%H:%M")
  filename = f"cover_letter_{timestamp}.pdf"
  await update.message.reply_document(document=InputFile(pdf_buffer, filename=filename))
  return ConversationHandler.END

# --- MAIN FUNCTION ---
def main():
  application = ApplicationBuilder().token(BOT_TOKEN).build()

  # Command and callback handlers 
  # application.add_handler(CommandHandler('start', start))
  application.add_handler(CommandHandler('unchecked', unchecked_handler))
  application.add_handler(CommandHandler('help', help_command))
  application.add_handler(CommandHandler('info', info_command))
  application.add_handler(CommandHandler('scrape', scrape_handler))
  application.add_handler(MessageHandler(filters.TEXT & filters.Entity("url"), handle_message))
  

  application.add_handler(CallbackQueryHandler(job_button_handler))
  
  
  pdf_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('pdf', pdf_command)],
    states={
      PDF_TEXT: [MessageHandler(filters.TEXT & (~filters.COMMAND), convert_to_pdf)],
    },
    fallbacks=[],
  )

  registration_conv_handler = ConversationHandler(
  entry_points=[CommandHandler('start', start)],
    states={
      RESUME_TEXT: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume)],
      EXPECTED_SALARY: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_expected_salary)],
      GRADUATION_DATE: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_graduation_date)],
    },
    fallbacks=[],
  )


  application.add_handler(pdf_conv_handler)
  application.add_handler(registration_conv_handler)

  application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
   main()
