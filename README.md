# Smart Cover Letter Agent — Personalized cover letters, faster

Turn any resume and job posting into a polished, tailored cover letter in seconds. Smart Cover Letter Agent combines your profile data with job details and AI-powered text generation so you can apply more, faster, and get better responses.

Why it helps:
- Save hours per application with instantly generated, role-specific cover letters.
- Write with confidence: professional tone, tailored highlights, and recruiter-friendly structure.
- Keep control: customize output, reuse templates, or fine-tune content per job.

Highlights:
- AI-powered personalization from your profile and job descriptions
- API-first backend for integration with UIs, pipelines, and automation
- Extensible: swap AI providers (Gemini or others) and add scraping or ATS integrations

Tech stack:
- Backend: Django 6 + Django REST Framework
- Frontend: Vite + React (see `front/SMART-COVER-LETTER-AGENT-FRONTEND`)
- Data: SQLite for local development (can be swapped for production DB)

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

3. Start the server:
```bash
python manage.py runserver
```

Server will run at: `http://127.0.0.1:8000/`

## Authentication System

The API uses **JWT (JSON Web Tokens)** for authentication.

### Available Endpoints

#### 1. Register
- **URL**: `POST /api/register/`
- **Permission**: Public
- **Request Body**:
```json
{
  "username": "john",
  "email": "john@example.com",
  "password": "securepass123",
  "password2": "securepass123"
}
```
- **Response** (201 Created):
```json
{
  "user": {
    "id": 1,
    "username": "john",
    "email": "john@example.com",
    "experience": "",
    "skills": [],
    "certificates": [],
    "preferred_jobs": ""
  },
  "refresh": "refresh_token_here",
  "access": "access_token_here"
}
```

#### 2. Login
- **URL**: `POST /api/login/`
- **Permission**: Public
- **Request Body**:
```json
{
  "username": "john",
  "password": "securepass123"
}
```
- **Response** (200 OK):
```json
{
  "refresh": "refresh_token_here",
  "access": "access_token_here"
}
```

#### 3. Logout
- **URL**: `POST /api/logout/`
- **Permission**: Authenticated
- **Headers**: `Authorization: Bearer <access_token>`
- **Request Body**:
```json
{
  "refresh": "refresh_token_here"
}
```
- **Response** (205 Reset Content):
```json
{
  "success": true
}
```

#### 4. Token Refresh
- **URL**: `POST /api/token/refresh/`
- **Permission**: Public
- **Request Body**:
```json
{
  "refresh": "refresh_token_here"
}
```
- **Response** (200 OK):
```json
{
  "access": "new_access_token_here"
}
```

#### 5. Get Profile
- **URL**: `GET /api/profile/`
- **Permission**: Authenticated
- **Headers**: `Authorization: Bearer <access_token>`
- **Response** (200 OK):
```json
{
  "experience": "5 years as a software developer...",
  "skills": ["Python", "Django", "JavaScript"],
  "certificates": ["AWS Certified", "Google Cloud"],
  "preferred_jobs": "Backend Developer, Full Stack Engineer"
}
```

#### 6. Update Profile
- **URL**: `PUT /api/profile/`
- **Permission**: Authenticated
- **Headers**: `Authorization: Bearer <access_token>`
- **Request Body**:
```json
{
  "experience": "5 years as a software developer...",
  "skills": ["Python", "Django", "JavaScript", "React"],
  "certificates": ["AWS Certified", "Google Cloud Professional"],
  "preferred_jobs": "Senior Backend Developer"
}
```
- **Response** (200 OK):
```json
{
  "success": true
}
```

## Testing with cURL

### Register a new user:
```bash
curl -X POST http://127.0.0.1:8000/api/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "TestPass123!",
    "password2": "TestPass123!"
  }'
```

### Login:
```bash
curl -X POST http://127.0.0.1:8000/api/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "TestPass123!"
  }'
```

### Get Profile (replace TOKEN with your access token):
```bash
curl -X GET http://127.0.0.1:8000/api/profile/ \
  -H "Authorization: Bearer TOKEN"
```

### Update Profile:
```bash
curl -X PUT http://127.0.0.1:8000/api/profile/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "experience": "I am a data scientist with 3 years of experience",
    "skills": ["Python", "Machine Learning", "Django"],
    "certificates": ["Data Science Certification"],
    "preferred_jobs": "Data Scientist, ML Engineer"
  }'
```

## Project Structure

```
smart-cover-letter-agent/
├── manage.py
├── requirements.txt
├── db.sqlite3
├── coverletter/          # Main project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── accounts/             # Authentication & user profiles
│   ├── models.py        # Custom User model
│   ├── serializers.py   # API serializers
│   ├── views.py         # API views
│   ├── urls.py          # URL routing
│   └── admin.py         # Admin configuration
├── jobs/                # Jobs & cover letter generation (to be implemented)
│   └── ...
└── old version/         # Previous Telegram bot code
    └── ...
```

## Next Steps

- [ ] Implement job listing endpoints
- [ ] Implement cover letter generation endpoint
- [ ] Integrate Gemini AI for cover letter generation
- [ ] Add job scraping functionality

## CORS Configuration

The API is configured to accept requests from:
- `http://localhost:3000` (React)
- `http://localhost:5173` (Vite)
- `http://127.0.0.1:3000`
- `http://127.0.0.1:5173`

Update `CORS_ALLOWED_ORIGINS` in `settings.py` if your frontend runs on a different port.
