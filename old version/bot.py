import json, os, logging, datetime, re, io, asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler
from scraper import Scraper 
from database import JobDatabase, UserDatabase
from urllib.parse import urlparse
from agent import Agent 
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.pagesizes import letter


# Load configuration from config.json
config_path = os.path.join(os.path.dirname(__file__), "config.json")
with open(config_path, "r") as config_file:
    config = json.load(config_file)

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or config.get('bot_token')

# --- SCRAPER AND DATABASE SETUP ---
scraper = Scraper()
job_db = JobDatabase("jobs.db")
user_db = UserDatabase("users.db")
agent = Agent()

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


UNCHECKED_LIMIT = 10

# --- HELPER FUNCTION FOR PDF GENERATION ---
def generate_pdf(text):
  """Generate a PDF from text and return a BytesIO buffer."""
  pdf_buffer = io.BytesIO()
  c = canvas.Canvas(pdf_buffer, pagesize=letter)
  width, height = letter
  left_margin = 50
  right_margin = 50
  top_margin = 50
  bottom_margin = 50
  usable_width = width - left_margin - right_margin
  y = height - top_margin

  paragraphs = text.split('\n')
  line_height = 14
  font_name = "Times-Roman"
  font_size = 12
  c.setFont(font_name, font_size)

  def ensure_space():
    nonlocal y
    if y < bottom_margin:
      c.showPage()
      c.setFont(font_name, font_size)
      y = height - top_margin

  def draw_line(line_text: str):
    nonlocal y
    c.drawString(left_margin, y, line_text)
    y -= line_height
    ensure_space()

  for para in paragraphs:
    if not para.strip():
      y -= line_height
      ensure_space()
      continue

    words = para.split()
    line = ""
    for word in words:
      test_line = f"{line} {word}".strip()
      if stringWidth(test_line, font_name, font_size) <= usable_width:
        line = test_line
      else:
        if line:
          draw_line(line)
        line = word

    if line:
      draw_line(line)

    y -= line_height
    ensure_space()

  c.save()
  pdf_buffer.seek(0)
  return pdf_buffer

PDF_TEXT = range(1)
(
  RESUME_NAME,
  RESUME_TITLE,
  RESUME_PHONE,
  RESUME_EMAIL,
  RESUME_LOCATION,
  RESUME_PORTFOLIO,
  RESUME_SKILLS,
  RESUME_EDUCATION,
  RESUME_LANGUAGES,
  RESUME_EXPERIENCE,
  RESUME_PROJECTS,
  RESUME_CERTS,
  EXPECTED_SALARY,
  GRADUATION_DATE,
) = range(1, 15)


def get_username(update: Update):
  return update.effective_user.username or str(update.effective_user.id)


async def require_registered(update: Update):
  username = get_username(update)
  user = user_db.get_user(username)
  if not user:
    await update.message.reply_text("Please register first with /start.")
    return None
  # Migrate any jobs stored under the numeric Telegram id to the canonical username
  try:
    numeric_id = str(update.effective_user.id)
    # Update jobs table rows where user_id == numeric_id to use the username key
    cursor = job_db.execute("UPDATE jobs SET user_id = ? WHERE user_id = ?", (username, numeric_id))
    if cursor.rowcount and cursor.rowcount > 0:
      logger.info(f"Migrated {cursor.rowcount} job rows from {numeric_id} to {username}")
  except Exception:
    # Non-critical; continue if migration fails
    pass
  return user


def normalize_optional(text: str):
  cleaned = (text or "").strip()
  if cleaned.lower() in {"skip", "none", "-"}:
    return ""
  return cleaned


def build_resume_text(data: dict):
  lines = []
  name = data.get('resume_name', '').strip()
  title = data.get('resume_title', '').strip()
  if name:
    lines.append(name)
  if title:
    lines.append(title)
  lines.append("")

  lines.append("CONTACT")
  if data.get('resume_phone'):
    lines.append(data['resume_phone'])
  if data.get('resume_email'):
    lines.append(data['resume_email'])
  if data.get('resume_location'):
    lines.append(data['resume_location'])
  if data.get('resume_portfolio'):
    lines.append(data['resume_portfolio'])
  lines.append("")

  if data.get('resume_skills'):
    lines.append("SKILLS")
    skills = [s.strip() for s in data['resume_skills'].split(',') if s.strip()]
    for skill in skills:
      lines.append(f"- {skill}")
    lines.append("")

  if data.get('resume_education'):
    lines.append("EDUCATION")
    lines.append(data['resume_education'])
    lines.append("")

  if data.get('resume_languages'):
    lines.append("LANGUAGES")
    lines.append(data['resume_languages'])
    lines.append("")

  if data.get('resume_experience'):
    lines.append("WORK EXPERIENCE")
    lines.append(data['resume_experience'])
    lines.append("")

  if data.get('resume_projects'):
    lines.append("PROJECTS")
    lines.append(data['resume_projects'])
    lines.append("")

  if data.get('resume_certs'):
    lines.append("CERTIFICATES")
    lines.append(data['resume_certs'])
    lines.append("")

  return "\n".join(lines).strip()


def get_source_label(link: str) -> str:
  domain = urlparse(link).netloc.replace('www.', '') if link else 'unknown'
  if 'linkedin' in domain:
    return 'LinkedIn'
  if 'stepstone' in domain:
    return 'StepStone'
  if 'stellenwerk' in domain:
    return 'Stellenwerk'
  return domain or 'unknown'


def extract_job_details_from_url(url: str):
  if 'stellenwerk.de' in url:
    soup = scraper.get_html(url)
    return scraper.extract_stellenwerk_details(soup)
  if 'linkedin.com' in url:
    return scraper.extract_linkedin_details(url)
  if 'stepstone.de' in url or 'offerView' in url:
    return scraper.extract_stepstone_details(url)
  return None


def build_job_action_keyboard(job_id: str, cover_letter_ready: bool = False):
  if cover_letter_ready:
    buttons = [[
      InlineKeyboardButton("Mark as seen", callback_data=f"seen:{job_id}"),
      InlineKeyboardButton("Create PDF", callback_data=f"pdf:{job_id}"),
    ]]
  else:
    buttons = [[
      InlineKeyboardButton("Mark as seen", callback_data=f"seen:{job_id}"),
      InlineKeyboardButton("Create cover letter", callback_data=f"cover:{job_id}"),
    ]]
  return InlineKeyboardMarkup(buttons)


# --- STARTUP MESSAGE ---
# --- USER REGISTRATION CONVERSATION HANDLER ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  username = get_username(update)
  user = user_db.get_user(username)
  if user:
    await update.message.reply_text(
      f"Hello {update.effective_user.first_name}, I am your job scraping bot! Use /help to see available commands."
    )
    return ConversationHandler.END
  else:
    await update.message.reply_text(f"Hello @{username}!\n\nIt seems like you are a new user. I need some information from you before you can use the bot.")
    await update.message.reply_text("Let's build your resume step by step.")
    await update.message.reply_text("Full name?")
    return RESUME_NAME

async def get_resume_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
  name = update.message.text.strip() if update.message.text else ""
  if len(name) < 2:
    await update.message.reply_text("Please enter your full name.")
    return RESUME_NAME
  context.user_data['resume_name'] = name
  await update.message.reply_text("Desired job title?")
  return RESUME_TITLE

async def get_resume_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
  title = update.message.text.strip() if update.message.text else ""
  if len(title) < 2:
    await update.message.reply_text("Please enter a job title.")
    return RESUME_TITLE
  context.user_data['resume_title'] = title
  await update.message.reply_text("Phone number?")
  return RESUME_PHONE

async def get_resume_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
  phone = update.message.text.strip() if update.message.text else ""
  if len(phone) < 5:
    await update.message.reply_text("Please enter a valid phone number.")
    return RESUME_PHONE
  context.user_data['resume_phone'] = phone
  await update.message.reply_text("Email address?")
  return RESUME_EMAIL

async def get_resume_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
  email_text = update.message.text.strip() if update.message.text else ""
  if '@' not in email_text:
    await update.message.reply_text("Please enter a valid email address.")
    return RESUME_EMAIL
  context.user_data['resume_email'] = email_text
  await update.message.reply_text("Location (city, country)?")
  return RESUME_LOCATION

async def get_resume_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
  location = update.message.text.strip() if update.message.text else ""
  if len(location) < 2:
    await update.message.reply_text("Please enter a location.")
    return RESUME_LOCATION
  context.user_data['resume_location'] = location
  await update.message.reply_text("Portfolio link? (send 'skip' to omit)")
  return RESUME_PORTFOLIO

async def get_resume_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data['resume_portfolio'] = normalize_optional(update.message.text)
  await update.message.reply_text("Skills (comma separated, e.g. Python, Django, SQL)?")
  return RESUME_SKILLS

async def get_resume_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
  skills = update.message.text.strip() if update.message.text else ""
  if len(skills) < 2:
    await update.message.reply_text("Please enter at least one skill.")
    return RESUME_SKILLS
  context.user_data['resume_skills'] = skills
  await update.message.reply_text("Education (e.g. University - Degree - Years)?")
  return RESUME_EDUCATION

async def get_resume_education(update: Update, context: ContextTypes.DEFAULT_TYPE):
  education = update.message.text.strip() if update.message.text else ""
  if len(education) < 3:
    await update.message.reply_text("Please enter your education details.")
    return RESUME_EDUCATION
  context.user_data['resume_education'] = education
  await update.message.reply_text("Languages (e.g. English C1, German B1)?")
  return RESUME_LANGUAGES

async def get_resume_languages(update: Update, context: ContextTypes.DEFAULT_TYPE):
  languages = update.message.text.strip() if update.message.text else ""
  if len(languages) < 2:
    await update.message.reply_text("Please enter at least one language.")
    return RESUME_LANGUAGES
  context.user_data['resume_languages'] = languages
  await update.message.reply_text("Work experience (brief summary, send 'skip' to omit)?")
  return RESUME_EXPERIENCE

async def get_resume_experience(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data['resume_experience'] = normalize_optional(update.message.text)
  await update.message.reply_text("Projects (brief summary, send 'skip' to omit)?")
  return RESUME_PROJECTS

async def get_resume_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data['resume_projects'] = normalize_optional(update.message.text)
  await update.message.reply_text("Certificates (brief summary, send 'skip' to omit)?")
  return RESUME_CERTS

async def get_resume_certs(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data['resume_certs'] = normalize_optional(update.message.text)
  resume_text = build_resume_text(context.user_data)
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
  username = get_username(update)

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
  username = get_username(update)
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


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
  logger.exception("Unhandled bot error", exc_info=context.error)
  if isinstance(update, Update) and update.effective_message:
    await update.effective_message.reply_text("Something went wrong. Please try again later.")


# --- HELP COMMAND HANDLER ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Here are the available commands:\n"
        "/start - Start the bot and register your information.\n"
        "/info - Get your registered information (resume, expected salary, graduation date).\n"
         "/list - Show your saved jobs and choose actions.\n"
    "/pdf - Convert text to PDF.\n"
    "/pdf_last - Legacy fallback for the last generated cover letter.\n"
        "/scrape - Manually trigger public job scraping from StepStone and Stellenwerk.\n"
         "Job links are no longer auto-processed. Use /list and the buttons on a saved job."
    )
    await update.message.reply_text(help_text)

# --- SCRAPE JOB FUNCTION ---
async def scrape_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user = await require_registered(update)
  if not user:
    return
  user_key = get_username(update)
  resume_text = user[3] or ""
  await update.message.reply_text("Starting scrape on StepStone, Stellenwerk and LinkedIn. This may take a while...")
  # run scrapers in thread pool (Playwright may be used for LinkedIn)
  stepstone_ok = await asyncio.to_thread(scraper.scrape_stepstone, user_key, resume_text)
  stellenwerk_ok = await asyncio.to_thread(scraper.scrape_stellenwerk, user_key, resume_text)
  linkedin_ok = False
  try:
    # LinkedIn scraper will try requests first, then Playwright if needed
    linkedin_ok = await asyncio.to_thread(scraper.scrape_linkedin, user_key, resume_text)
  except Exception as exc:
    print(f"[WARNING] LinkedIn scrape raised: {exc}")

  await update.message.reply_text("Scrape completed. Use /list to see saved jobs.")

  if stepstone_ok or stellenwerk_ok or linkedin_ok:
    await update.message.reply_text("✅ Scraping completed from public job pages.")
  else:
    await update.message.reply_text("❌ Scraping failed.")

async def list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """List saved jobs for the calling user, showing a few items per source."""
  user = await require_registered(update)
  if not user:
    return
  username = get_username(update)
  rows = job_db.fetchall('SELECT id, title, link, checked FROM jobs WHERE user_id = ? AND checked = 0 ORDER BY id DESC', (username,))
  if not rows:
    await update.message.reply_text("You have no saved jobs. Run /scrape to discover jobs.")
    return

  # Group by domain/source and show up to N per source
  per_source_limit = 5
  grouped = {}
  for jid, title, link, checked in rows:
    src = get_source_label(link)
    grouped.setdefault(src, []).append((jid, title, link))

  keyboard = []
  for src in sorted(grouped.keys()):
    for jid, title, link in grouped[src][:per_source_limit]:
      label = f"[{src}] {title}"
      keyboard.append([InlineKeyboardButton(label, callback_data=f"view:{jid}")])

  reply_markup = InlineKeyboardMarkup(keyboard)
  total = len(rows)
  shown = sum(min(len(v), per_source_limit) for v in grouped.values())
  note = f"Showing {shown} of {total} (up to {per_source_limit} per source)."
  await update.message.reply_text(f"Select a job to get the link: {note}", reply_markup=reply_markup)

# --- CALLBACK FOR BUTTON PRESS ---
async def job_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  user_id = (query.from_user.username or str(query.from_user.id))
  data = query.data or ""

  if data.startswith('view:'):
    job_id = data.split(':', 1)[1]
    job = job_db.get_job_by_id(job_id, user_id)
    if not job:
      await query.edit_message_text(text="Job not found for your account.")
      return
    await query.edit_message_text(
      text=f"{job[1]}\n\n{job[2]}",
      reply_markup=build_job_action_keyboard(job_id, cover_letter_ready=False),
      disable_web_page_preview=True,
    )
    return

  if data.startswith('seen:'):
    job_id = data.split(':', 1)[1]
    job = job_db.get_job_by_id(job_id, user_id)
    if not job:
      await query.edit_message_text(text="Job not found for your account.")
      return
    job_db.mark_job_as_checked(job_id, user_id)
    await query.edit_message_text(text=f"Marked as seen. Removed from /list.\n\n{job[1]}")
    return

  if data.startswith('cover:'):
    job_id = data.split(':', 1)[1]
    job = job_db.get_job_by_id(job_id, user_id)
    if not job:
      await query.edit_message_text(text="Job not found for your account.")
      return
    user = await require_registered(update)
    if not user:
      return
    resume_text = user[3] or ""
    if not resume_text:
      await query.edit_message_text(text="Please register your resume first.")
      return

    try:
      job_details = await asyncio.to_thread(extract_job_details_from_url, job[2])
      if not job_details:
        await query.edit_message_text(text="Sorry, I could not extract job details from that link.")
        return
      message = await asyncio.to_thread(agent.send_request, job_details, resume_text)
      if message == 'The model is overloaded. Please try again later.':
        await query.edit_message_text(text=message)
        return
      generated = context.user_data.setdefault('generated_cover_letters', {})
      generated[job_id] = message
      context.user_data['last_cover_letter'] = message
      await query.edit_message_text(
        text=message,
        reply_markup=build_job_action_keyboard(job_id, cover_letter_ready=True),
        disable_web_page_preview=True,
      )
    except Exception as exc:
      await query.message.reply_text(f"Failed to create cover letter: {exc}")
    return

  if data.startswith('pdf:'):
    job_id = data.split(':', 1)[1]
    generated = context.user_data.get('generated_cover_letters', {})
    cover_letter = generated.get(job_id) or context.user_data.get('last_cover_letter')
    if not cover_letter:
      await query.edit_message_text(text="No generated cover letter found. Create one first.")
      return
    pdf_buffer = generate_pdf(cover_letter)
    timestamp = datetime.datetime.now().strftime("%m_%d_%H:%M")
    filename = f"cover_letter_{timestamp}.pdf"
    await query.message.reply_document(document=InputFile(pdf_buffer, filename=filename))
    return

  await query.edit_message_text(text="Unknown action.")


async def pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user = await require_registered(update)
  if not user:
    return ConversationHandler.END
  await update.message.reply_text("Please send the text you want to convert to PDF.")
  return PDF_TEXT

async def convert_to_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
  message_text = update.message.text
  if not message_text:
    await update.message.reply_text("No text to convert to PDF.")
    return ConversationHandler.END

  # Generate PDF using helper function
  pdf_buffer = generate_pdf(message_text)
  
  timestamp = datetime.datetime.now().strftime("%m_%d_%H:%M")
  filename = f"cover_letter_{timestamp}.pdf"
  await update.message.reply_document(document=InputFile(pdf_buffer, filename=filename))
  return ConversationHandler.END


async def claim_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """Migrate any jobs stored under the numeric Telegram id to the user's canonical username."""
  username = get_username(update)
  numeric_id = str(update.effective_user.id)
  try:
    cursor = job_db.execute("SELECT COUNT(*) FROM jobs WHERE user_id = ?", (numeric_id,))
    count = cursor.fetchone()[0]
    if count and count > 0:
      job_db.execute("UPDATE jobs SET user_id = ? WHERE user_id = ?", (username, numeric_id))
      await update.message.reply_text(f"Claimed {count} jobs previously linked to your numeric id.")
    else:
      await update.message.reply_text("No jobs found under your numeric Telegram id.")
  except Exception as exc:
    await update.message.reply_text(f"Error while claiming jobs: {exc}")


async def dedupe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """Remove duplicate job entries for the calling user."""
  user = await require_registered(update)
  if not user:
    return
  username = get_username(update)
  try:
    deleted = job_db.dedupe_jobs(username)
    await update.message.reply_text(f"Dedupe complete. Removed {deleted} duplicate job(s).")
  except Exception as exc:
    await update.message.reply_text(f"Dedupe failed: {exc}")

async def pdf_last_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user = await require_registered(update)
  if not user:
    return
  last_text = context.user_data.get('last_cover_letter')
  if not last_text:
    await update.message.reply_text("No recent cover letter found. Send a job link first.")
    return

  pdf_buffer = generate_pdf(last_text)
  timestamp = datetime.datetime.now().strftime("%m_%d_%H:%M")
  filename = f"cover_letter_{timestamp}.pdf"
  await update.message.reply_document(document=InputFile(pdf_buffer, filename=filename))

# --- MAIN FUNCTION ---
def main():
  missing = []
  if not BOT_TOKEN:
    missing.append('bot_token')
  if not (config.get('groq_api_key') or config.get('api_key')):
    missing.append('groq_api_key or api_key')
  if missing:
    logger.error("Missing required config keys: %s", ", ".join(missing))
    raise SystemExit(1)

  application = ApplicationBuilder().token(BOT_TOKEN).build()

  # Command and callback handlers 
  # application.add_handler(CommandHandler('start', start))
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
      RESUME_NAME: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume_name)],
      RESUME_TITLE: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume_title)],
      RESUME_PHONE: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume_phone)],
      RESUME_EMAIL: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume_email)],
      RESUME_LOCATION: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume_location)],
      RESUME_PORTFOLIO: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume_portfolio)],
      RESUME_SKILLS: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume_skills)],
      RESUME_EDUCATION: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume_education)],
      RESUME_LANGUAGES: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume_languages)],
      RESUME_EXPERIENCE: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume_experience)],
      RESUME_PROJECTS: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume_projects)],
      RESUME_CERTS: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_resume_certs)],
      EXPECTED_SALARY: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_expected_salary)],
      GRADUATION_DATE: [MessageHandler(filters.TEXT & (~filters.COMMAND), get_graduation_date)],
    },
    fallbacks=[],
  )

  # Conversation handlers first to avoid URL handler hijacking registration replies.
  application.add_handler(registration_conv_handler)
  application.add_handler(pdf_conv_handler)
  application.add_handler(CommandHandler('list', list_handler))
  application.add_handler(CommandHandler('help', help_command))
  application.add_handler(CommandHandler('info', info_command))
  application.add_handler(CommandHandler('scrape', scrape_handler))
  application.add_handler(CommandHandler('claimjobs', claim_jobs))
  application.add_handler(CommandHandler('dedupe', dedupe_command))
  application.add_handler(CommandHandler('pdf_last', pdf_last_command))

  application.add_handler(CallbackQueryHandler(job_button_handler))
  application.add_error_handler(error_handler)

  application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
   main()
