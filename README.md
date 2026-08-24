# ExpiryGuard — Secure Backend & Web Dashboard

ExpiryGuard is a pharmacy intelligence platform designed to prevent medicine expiry waste and automate pharmacy operations. It features real-time inventory tracking, AI-powered OCR label and invoice scanning (via Google Gemini), automated WhatsApp/FCM push expiry alerts, and GST-compliant invoicing/billing.

---

## 🛠️ Technology Stack
- **Backend**: Python 3.11 with FastAPI (Asynchronous Web Framework)
- **Database**: PostgreSQL (SQLAlchemy ORM + migration capabilities)
- **AI Engine**: Google Gemini API (gemini-flash-latest) for OCR invoice and packaging scans
- **Push Engine**: Firebase Cloud Messaging (FCM)
- **Frontend Dashboard**: Native HTML5, CSS3, and modern ES6 Javascript (located in `/web` and `/public_site`)
- **Task Scheduling**: APScheduler (Interval tasks for notifications & data cleanup)

---

## 📂 Project Structure
- `/app.py`: FastAPI server entrypoint (routes, middleware, exception handlers).
- `/crud.py`: Database operations and business logic mapping.
- `/models.py` & `/schemas.py`: SQLAlchemy database models & Pydantic verification schemas.
- `/database.py`: DB engine connection pool and session settings.
- `/email_service.py`: SMTP-based transaction notifier.
- `/notification_service.py`: FCM Push notification processor.
- `/scheduler.py`: Background cron manager.
- `/web/`: Dashboard app frontend.
- `/public_site/`: Public product landing page.
- `/flutter/lib/`: Mobile companion app source code.
- `/requirements.txt`: Python package dependencies list.

---

## ⚙️ Environment Setup & Installation

### 1. Restore & Install Dependencies
Ensure you have Python 3.11 installed. Create a clean virtual environment and install packages:
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 2. Configure Local Environment
Copy the example file to `.env` and fill in your keys:
```bash
cp .env.example .env
```
Ensure you set:
- `DATABASE_URL`: Your PostgreSQL database connection string.
- `SECRET_KEY`: JWT session generation salt.
- `GEMINI_API_KEY`: Google Gemini API key.
- `SMTP_USER` & `SMTP_PASS`: SMTP credentials for email alerts.

*Note: Firebase Service account details should be placed inside `credentials/firebase_key.json` as specified in your configuration.*

---

## 🚀 Running the Project

### Start the Backend Server
```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```
FastAPI automatically handles database migrations and starts background schedulers upon initialization.

The web app is accessible at `http://localhost:8000/web/` and the public site at `http://localhost:8000/`.
