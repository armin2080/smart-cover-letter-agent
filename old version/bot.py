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
ADMIN_ID = config.get('user_id')  # Telegram user ID of the bot admin

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

# --- EDIT CONVERSATION STATES ---
(
    EDIT_CHOICE,
    EDIT_RESUME_NAME,
    EDIT_RESUME_TITLE,
    EDIT_RESUME_PHONE,
    EDIT_RESUME_EMAIL,
    EDIT_RESUME_LOCATION,
    EDIT_RESUME_PORTFOLIO,
    EDIT_RESUME_SKILLS,
    EDIT_RESUME_EDUCATION,
    EDIT_RESUME_LANGUAGES,
    EDIT_RESUME_EXPERIENCE,
    EDIT_RESUME_PROJECTS,
    EDIT_RESUME_CERTS,
    EDIT_EXPECTED_SALARY,
    EDIT_GRADUATION_DATE,
) = range(15, 30)


def get_username(update: Update):
  return update.effective_user.username or str(update.effective_user.id)


async def require_registered(update: Update):
  username = get_username(update)
  user = user_db.get_user(username)
  if not user:
    await update.message.reply_text("Please register first with /start.")
    return None
  # Store chat_id for this user so admin announcements can reach them
  try:
    chat_id = update.effective_chat.id
    user_db.set_chat_id(username, chat_id)
  except Exception:
    pass
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
  # Save individual resume fields
  resume_fields = {field: context.user_data.get(field) for field in user_db.RESUME_FIELDS}
  user_db.save_resume_fields(username, resume_fields)
  await update.message.reply_text("Thank you! Your data has been saved. You can now use the bot. Use /help to see available commands.")
  return ConversationHandler.END


# (/info is handled by the edit ConversationHandler — see info_command)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
  logger.exception("Unhandled bot error", exc_info=context.error)
  if isinstance(update, Update) and update.effective_message:
    await update.effective_message.reply_text("Something went wrong. Please try again later.")


# --- HELP COMMAND HANDLER ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Here are the available commands:\n"
        "/start - Start the bot and register your information.\n"
        "/info - View your profile and edit it with the ✏️ button.\n"
        "/filter - Set your preferred job types (full-time, part-time, working student, etc.).\n"
        "/list - Show your saved jobs (filtered by your preferences).\n"
        "/scrape - Manually trigger public job scraping from StepStone and Stellenwerk.\n"
        "/pdf - Convert text to PDF.\n"
        "/pdf_last - Legacy fallback for the last generated cover letter.\n"
        "Job links are no longer auto-processed. Use /list and the buttons on a saved job."
    )
    if is_admin(update):
        help_text += (
            "\n\n👑 <b>Admin commands:</b>\n"
            "/announce - Send an announcement to all registered users.\n"
            "/stats - List all registered users."
        )
    await update.message.reply_text(help_text, parse_mode='HTML')

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
  
  # Get user's preferred job types
  preferred_types = user_db.get_preferred_types(username)
  
  # Fetch jobs matching preferred types
  rows = job_db.fetchall(
      'SELECT id, title, link, checked, employment_type FROM jobs WHERE user_id = ? AND checked = 0 ORDER BY id DESC',
      (username,)
  )
  
  # Filter by preferred employment types
  if preferred_types:
      rows = [r for r in rows if r[4] is None or r[4] in preferred_types]
  
  if not rows:
    preferred_labels = ', '.join(preferred_types) if preferred_types else 'any'
    await update.message.reply_text(
        f"No saved jobs match your filter ({preferred_labels}). "
        f"Run /scrape to discover jobs or use /filter to change your preferences."
    )
    return

  # Group by domain/source and show up to N per source
  per_source_limit = 5
  grouped = {}
  for jid, title, link, checked, emp_type in rows:
    src = get_source_label(link)
    grouped.setdefault(src, []).append((jid, title, link, emp_type))

  keyboard = []
  for src in sorted(grouped.keys()):
    for jid, title, link, emp_type in grouped[src][:per_source_limit]:
      badge = {
          'fulltime': '👔', 'parttime': '🕐', 'workingstudent': '🎓',
          'internship': '📋', 'minijob': '💼',
      }.get(emp_type, '📌') if emp_type else '📌'
      label = f"{badge} [{src}] {title}"
      keyboard.append([InlineKeyboardButton(label, callback_data=f"view:{jid}")])

  reply_markup = InlineKeyboardMarkup(keyboard)
  total = len(rows)
  shown = sum(min(len(v), per_source_limit) for v in grouped.values())
  filter_note = f"Filter: {', '.join(preferred_types)}" if preferred_types else "No filter"
  note = f"Showing {shown} of {total} (up to {per_source_limit} per source). {filter_note}"
  await update.message.reply_text(f"Select a job to get the link:\n{note}", reply_markup=reply_markup)

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

# --- /info COMMAND HANDLER (with inline edit button) ---
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show profile with an ✏️ Edit Profile button."""
    user = await require_registered(update)
    if not user:
        return ConversationHandler.END
    
    resume_text = user[3] or "Not set yet."
    salary = user[4] or "Not set"
    grad_date = user[5] or "Not set"
    
    info_text = (
        f"📋 <b>Your Profile</b>\n\n"
        f"<b>Resume:</b>\n{resume_text}\n\n"
        f"<b>Expected Salary:</b> {salary} EUR/hour\n"
        f"<b>Graduation Date:</b> {grad_date}"
    )
    
    keyboard = [[InlineKeyboardButton("✏️ Edit Profile", callback_data="edit_field:start")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(info_text, reply_markup=reply_markup, parse_mode='HTML')
    return EDIT_CHOICE


async def edit_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the field selection from inline keyboard."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "edit_field:cancel":
        await query.edit_message_text("Edit cancelled.")
        return ConversationHandler.END
    
    if data == "edit_field:start":
        # User clicked "Edit Profile" from /info — show field selection keyboard
        keyboard = [
            [InlineKeyboardButton("📝 Full Name", callback_data="edit_field:resume_name")],
            [InlineKeyboardButton("📝 Job Title", callback_data="edit_field:resume_title")],
            [InlineKeyboardButton("📝 Phone", callback_data="edit_field:resume_phone")],
            [InlineKeyboardButton("📝 Email", callback_data="edit_field:resume_email")],
            [InlineKeyboardButton("📝 Location", callback_data="edit_field:resume_location")],
            [InlineKeyboardButton("📝 Portfolio", callback_data="edit_field:resume_portfolio")],
            [InlineKeyboardButton("📝 Skills", callback_data="edit_field:resume_skills")],
            [InlineKeyboardButton("📝 Education", callback_data="edit_field:resume_education")],
            [InlineKeyboardButton("📝 Languages", callback_data="edit_field:resume_languages")],
            [InlineKeyboardButton("📝 Experience", callback_data="edit_field:resume_experience")],
            [InlineKeyboardButton("📝 Projects", callback_data="edit_field:resume_projects")],
            [InlineKeyboardButton("📝 Certificates", callback_data="edit_field:resume_certs")],
            [InlineKeyboardButton("💰 Expected Salary", callback_data="edit_field:expected_salary")],
            [InlineKeyboardButton("📅 Graduation Date", callback_data="edit_field:graduation_date")],
            [InlineKeyboardButton("❌ Cancel", callback_data="edit_field:cancel")],
        ]
        await query.edit_message_text(
            "Select a field to edit:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return EDIT_CHOICE
    
    field = data.split(":", 1)[1] if ":" in data else None
    if not field:
        await query.edit_message_text("Invalid selection.")
        return ConversationHandler.END
    
    context.user_data['edit_field'] = field
    
    # Get current value
    username = get_username(update)
    
    if field in user_db.RESUME_FIELDS:
        resume_fields = user_db.get_resume_fields(username)
        current_value = resume_fields.get(field, "") if resume_fields else ""
    elif field == 'expected_salary':
        user = user_db.get_user(username)
        current_value = str(user[4]) if user and user[4] else ""
    elif field == 'graduation_date':
        user = user_db.get_user(username)
        current_value = str(user[5]) if user and user[5] else ""
    else:
        current_value = ""
    
    label = user_db.RESUME_FIELD_LABELS.get(field, field)
    current_display = current_value if current_value else "Not set"
    
    await query.edit_message_text(
        f"Editing: <b>{label}</b>\n\n"
        f"Current value: <code>{current_display}</code>\n\n"
        f"Please send the new value (or send /cancel to abort):",
        parse_mode='HTML'
    )
    
    # Map field to the right state
    field_to_state = {
        'resume_name': EDIT_RESUME_NAME,
        'resume_title': EDIT_RESUME_TITLE,
        'resume_phone': EDIT_RESUME_PHONE,
        'resume_email': EDIT_RESUME_EMAIL,
        'resume_location': EDIT_RESUME_LOCATION,
        'resume_portfolio': EDIT_RESUME_PORTFOLIO,
        'resume_skills': EDIT_RESUME_SKILLS,
        'resume_education': EDIT_RESUME_EDUCATION,
        'resume_languages': EDIT_RESUME_LANGUAGES,
        'resume_experience': EDIT_RESUME_EXPERIENCE,
        'resume_projects': EDIT_RESUME_PROJECTS,
        'resume_certs': EDIT_RESUME_CERTS,
        'expected_salary': EDIT_EXPECTED_SALARY,
        'graduation_date': EDIT_GRADUATION_DATE,
    }
    return field_to_state.get(field, EDIT_CHOICE)


async def handle_edit_text_field(update: Update, context: ContextTypes.DEFAULT_TYPE, field: str):
    """Generic handler for editing a text resume field."""
    new_value = update.message.text.strip() if update.message.text else ""
    if not new_value:
        await update.message.reply_text("Value cannot be empty. Please send a non-empty value or use /cancel.")
        return None  # stay in same state
    
    username = get_username(update)
    user_db.update_resume_field(username, field, new_value)
    
    # Rebuild the full resume text
    resume_fields = user_db.get_resume_fields(username)
    if resume_fields:
        # Build a dict with all fields for build_resume_text
        field_data = {}
        for f in user_db.RESUME_FIELDS:
            field_data[f] = resume_fields.get(f) or ""
        # Add any non-resume fields from the user record
        user = user_db.get_user(username)
        field_data['expected_salary'] = user[4] if user else None
        field_data['graduation_date'] = user[5] if user else None
        new_resume = build_resume_text(field_data)
        user_db.update_user(username, resume=new_resume)
    
    label = user_db.RESUME_FIELD_LABELS.get(field, field)
    await update.message.reply_text(f"✅ <b>{label}</b> updated successfully!", parse_mode='HTML')
    return ConversationHandler.END


async def edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_edit_text_field(update, context, 'resume_name')

async def edit_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_edit_text_field(update, context, 'resume_title')

async def edit_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_edit_text_field(update, context, 'resume_phone')

async def edit_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_edit_text_field(update, context, 'resume_email')

async def edit_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_edit_text_field(update, context, 'resume_location')

async def edit_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_edit_text_field(update, context, 'resume_portfolio')

async def edit_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_edit_text_field(update, context, 'resume_skills')

async def edit_education(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_edit_text_field(update, context, 'resume_education')

async def edit_languages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_edit_text_field(update, context, 'resume_languages')

async def edit_experience(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_edit_text_field(update, context, 'resume_experience')

async def edit_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_edit_text_field(update, context, 'resume_projects')

async def edit_certs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_edit_text_field(update, context, 'resume_certs')


async def edit_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle editing expected salary."""
    salary_text = update.message.text.strip() if update.message.text else ""
    try:
        salary = int(salary_text.replace(",", "").replace(".", ""))
        if salary <= 0:
            raise ValueError("Salary must be a positive number.")
    except Exception:
        await update.message.reply_text("Please enter a valid number for your expected salary (e.g. 15).")
        return EDIT_EXPECTED_SALARY
    
    username = get_username(update)
    user_db.update_resume_field(username, 'expected_salary', salary)
    user_db.update_user(username, expected_salary=salary)
    
    await update.message.reply_text(f"✅ <b>Expected Salary</b> updated to {salary} EUR/hour!", parse_mode='HTML')
    return ConversationHandler.END


async def edit_graduation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle editing graduation date."""
    date_text = update.message.text.strip() if update.message.text else ""
    try:
        grad_date = datetime.datetime.strptime(date_text, "%Y.%m.%d").date()
    except Exception:
        await update.message.reply_text("Please enter the date in the format YYYY.MM.DD (e.g. 2026.07.01).")
        return EDIT_GRADUATION_DATE
    
    username = get_username(update)
    user_db.update_resume_field(username, 'graduation_date', str(grad_date))
    user_db.update_user(username, graduation_date=str(grad_date))
    
    await update.message.reply_text(f"✅ <b>Graduation Date</b> updated to {grad_date}!", parse_mode='HTML')
    return ConversationHandler.END


async def edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the edit conversation."""
    await update.message.reply_text("Edit cancelled.")
    return ConversationHandler.END


async def edit_choice_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback for unexpected messages during edit choice."""
    await update.message.reply_text("Please select a field from the keyboard above or use /cancel.")
    return EDIT_CHOICE

# --- ADMIN STATS ---
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show registered users (admin only)."""
    if not is_admin(update):
        await update.message.reply_text("⛔ This command is only available to the bot admin.")
        return
    
    rows = user_db.fetchall('SELECT name, username FROM users ORDER BY name')
    if not rows:
        await update.message.reply_text("No registered users yet.")
        return
    
    total = len(rows)
    lines = [f"👥 <b>Registered Users ({total})</b>\n"]
    for i, (name, username) in enumerate(rows, 1):
        display_name = (name or '').strip() or '—'
        lines.append(f"{i}. {display_name} (@{username})")
    
    # Send in chunks if too long (Telegram limit ~4000 chars)
    text = '\n'.join(lines)
    if len(text) <= 4000:
        await update.message.reply_text(text, parse_mode='HTML')
    else:
        # Split into multiple messages
        for chunk in [text[i:i+3500] for i in range(0, len(text), 3500)]:
            await update.message.reply_text(chunk, parse_mode='HTML')


# --- ADMIN ANNOUNCEMENT ---
ANNOUNCE_TEXT, ANNOUNCE_CONFIRM = range(30, 32)


def is_admin(update: Update) -> bool:
    """Check if the user is the bot admin."""
    user_id = update.effective_user.id
    return user_id == ADMIN_ID


async def announce_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the announcement flow (admin only)."""
    if not is_admin(update):
        await update.message.reply_text("⛔ This command is only available to the bot admin.")
        return ConversationHandler.END
    
    # Store admin's chat_id so they receive the announcement too
    try:
        user_db.set_chat_id(get_username(update), update.effective_chat.id)
    except Exception:
        pass
    
    await update.message.reply_text(
        "📢 <b>Send the announcement message</b>\n\n"
        "Type the message you want to send to all registered users.\n"
        "Send /cancel to abort.",
        parse_mode='HTML'
    )
    return ANNOUNCE_TEXT


async def announce_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the announcement flow."""
    await update.message.reply_text("Announcement cancelled.")
    return ConversationHandler.END


async def announce_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the text and show a preview with confirm/cancel buttons."""
    message_text = update.message.text.strip() if update.message.text else ""
    if not message_text:
        await update.message.reply_text("Message cannot be empty. Please type your announcement.")
        return ANNOUNCE_TEXT
    
    # Store the text for later use
    context.user_data['announce_text'] = message_text
    
    # Count all users (we'll try sending to everyone, with/without chat_id)
    all_users = user_db.fetchall('SELECT username, chat_id FROM users')
    with_chat = sum(1 for _, cid in all_users if cid is not None)
    without_chat = sum(1 for _, cid in all_users if cid is None)
    
    preview = (
        f"📢 <b>Announcement Preview</b>\n\n"
        f"{message_text}\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Total users: <b>{len(all_users)}</b>\n"
        f"With chat_id: {with_chat} | Without: {without_chat}"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Send", callback_data="announce_confirm:yes"),
            InlineKeyboardButton("❌ Cancel", callback_data="announce_confirm:no"),
        ]
    ]
    
    await update.message.reply_text(preview, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return ANNOUNCE_CONFIRM


async def announce_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the Send/Cancel decision."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "announce_confirm:no":
        await query.edit_message_text("Announcement cancelled.")
        return ConversationHandler.END
    
    # Proceed to send
    message_text = context.user_data.get('announce_text', '')
    await query.edit_message_text("📤 Sending announcement to all users...")
    
    all_users = user_db.fetchall('SELECT username, chat_id FROM users')
    sent = 0
    failed = 0
    errors = []
    
    for username, chat_id in all_users:
        try:
            if chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"📢 <b>Announcement</b>\n\n{message_text}",
                    parse_mode='HTML'
                )
                sent += 1
            else:
                # Can't reach users without a stored chat_id
                failed += 1
                errors.append(f"{username}: no chat_id (user must send a command first)")
        except Exception as e:
            failed += 1
            errors.append(f"{username}: {e}")
    
    report = (
        f"📊 <b>Announcement Results</b>\n\n"
        f"Total users: {len(all_users)}\n"
        f"✅ Sent: {sent}\n"
        f"❌ Failed: {failed}"
    )
    if errors:
        report += f"\n\nFirst errors:\n" + "\n".join(str(e) for e in errors[:5])
    
    await context.bot.send_message(chat_id=query.from_user.id, text=report, parse_mode='HTML')
    return ConversationHandler.END


# --- FILTER COMMAND ---
async def filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current job type filter and allow toggling types."""
    user = await require_registered(update)
    if not user:
        return
    username = get_username(update)
    preferred = user_db.get_preferred_types(username)
    
    text = "🔍 <b>Job Type Filter</b>\n\nSelect which job types you want to see:\n"
    keyboard = []
    for t in job_db.EMPLOYMENT_TYPES:
        label = {
            'fulltime': '👔 Full-Time',
            'parttime': '🕐 Part-Time',
            'workingstudent': '🎓 Working Student',
            'internship': '📋 Internship',
            'minijob': '💼 Minijob',
        }.get(t, t)
        checked = "✅" if t in preferred else "⬜"
        keyboard.append([InlineKeyboardButton(f"{checked} {label}", callback_data=f"filter_toggle:{t}")])
    keyboard.append([InlineKeyboardButton("✅ Done", callback_data="filter_done")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def filter_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle toggle/done on filter keyboard."""
    query = update.callback_query
    await query.answer()
    data = query.data
    username = query.from_user.username or str(query.from_user.id)
    
    if data == "filter_done":
        await query.edit_message_text("✅ Filter updated!")
        return
    
    if data.startswith("filter_toggle:"):
        emp_type = data.split(":", 1)[1]
        preferred = user_db.get_preferred_types(username)
        if emp_type in preferred:
            preferred = [t for t in preferred if t != emp_type]
        else:
            preferred.append(emp_type)
        user_db.set_preferred_types(username, preferred)
        
        # Rebuild keyboard with updated toggles
        text = "🔍 <b>Job Type Filter</b>\n\nSelect which job types you want to see:\n"
        keyboard = []
        for t in job_db.EMPLOYMENT_TYPES:
            label = {
                'fulltime': '👔 Full-Time',
                'parttime': '🕐 Part-Time',
                'workingstudent': '🎓 Working Student',
                'internship': '📋 Internship',
                'minijob': '💼 Minijob',
            }.get(t, t)
            checked = "✅" if t in preferred else "⬜"
            keyboard.append([InlineKeyboardButton(f"{checked} {label}", callback_data=f"filter_toggle:{t}")])
        keyboard.append([InlineKeyboardButton("✅ Done", callback_data="filter_done")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


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

  # --- EDIT CONVERSATION HANDLER (entry via /info button) ---
  edit_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('info', info_command)],
    states={
      EDIT_CHOICE: [CallbackQueryHandler(edit_choice_handler, pattern="^edit_field:")],
      EDIT_RESUME_NAME: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_name)],
      EDIT_RESUME_TITLE: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_title)],
      EDIT_RESUME_PHONE: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_phone)],
      EDIT_RESUME_EMAIL: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_email)],
      EDIT_RESUME_LOCATION: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_location)],
      EDIT_RESUME_PORTFOLIO: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_portfolio)],
      EDIT_RESUME_SKILLS: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_skills)],
      EDIT_RESUME_EDUCATION: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_education)],
      EDIT_RESUME_LANGUAGES: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_languages)],
      EDIT_RESUME_EXPERIENCE: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_experience)],
      EDIT_RESUME_PROJECTS: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_projects)],
      EDIT_RESUME_CERTS: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_certs)],
      EDIT_EXPECTED_SALARY: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_salary)],
      EDIT_GRADUATION_DATE: [MessageHandler(filters.TEXT & (~filters.COMMAND), edit_graduation)],
    },
    fallbacks=[CommandHandler('cancel', edit_cancel)],
  )

  # --- ANNOUNCEMENT CONVERSATION HANDLER (admin only) ---
  announce_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('announce', announce_command)],
    states={
      ANNOUNCE_TEXT: [MessageHandler(filters.TEXT & (~filters.COMMAND), announce_send)],
      ANNOUNCE_CONFIRM: [CallbackQueryHandler(announce_confirm_handler, pattern="^announce_confirm:")],
    },
    fallbacks=[CommandHandler('cancel', announce_cancel)],
  )

  # Conversation handlers first to avoid URL handler hijacking registration replies.
  application.add_handler(announce_conv_handler)
  application.add_handler(registration_conv_handler)
  application.add_handler(edit_conv_handler)
  application.add_handler(pdf_conv_handler)
  application.add_handler(CommandHandler('list', list_handler))
  application.add_handler(CommandHandler('help', help_command))
  # /info is handled by edit_conv_handler above
  application.add_handler(CommandHandler('stats', stats_command))
  application.add_handler(CommandHandler('filter', filter_command))
  application.add_handler(CommandHandler('scrape', scrape_handler))
  application.add_handler(CommandHandler('claimjobs', claim_jobs))
  application.add_handler(CommandHandler('dedupe', dedupe_command))
  application.add_handler(CommandHandler('pdf_last', pdf_last_command))

  application.add_handler(CallbackQueryHandler(filter_button_handler, pattern="^filter_"))
  application.add_handler(CallbackQueryHandler(job_button_handler))
  application.add_error_handler(error_handler)

  application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
   main()
