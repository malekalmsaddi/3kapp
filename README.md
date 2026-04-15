# 🧠 Moeen AI — Multi-Channel Conversational Assistant

**Moeen AI** is an AI-powered assistant that integrates WhatsApp and Telegram using OpenAI's GPT-4 API, enriched with persistent thread memory, SendGrid emailing, calendar booking, and scalable bulk messaging. It supports administrative tools with real-time dashboards.

> **Stack**: Flask + Celery + Redis + PostgreSQL

---

## ✨ Core Features

### 🤖 AI Assistant Engine
- GPT-4 via Assistant API with persistent thread memory
- Auto tool calls: `send_email`, `create_calendar_event`, `get_available_time_slots`
- Arabic/English prompt support
- Multi-thread safe, duplicate-handling logic

### 📲 Messaging Integrations
- WhatsApp messaging via Twilio (Content API and template system) with optional Messaging Service SID
- Telegram bot (async)
- Rate-limited via Redis, with deduplication
- Message logging to PostgreSQL

### ⚙️ Admin & Monitoring Tools
- **Admin Dashboard**: bulk logs, Redis keys, OpenAI threads, recent messages
- **Send Templates**: CSV preview, contact selection, real-time delivery feedback
- **Real-Time Metrics**: live message statistics visualized with Chart.js
- Health checks: `/health`, `/metrics`, task status endpoint
- Secure login with bcrypt and CSRF protection
- Colorized logging with adjustable verbosity via `LOG_LEVEL`
- Third-party loggers like Twilio are capped at `WARNING`

## 🌐 Front-End Migration to Next.js

The legacy Flask templates will be replaced with a Next.js application styled with a **Glassmorphism Red** theme. Progress and detailed steps are tracked in [MIGRATION.md](MIGRATION.md).

The design system now includes a Glassmorphism Red color palette, Inter typography, and a reusable `GlassPanel` component.

The app now features a cookie-based `AuthGuard`, server-side middleware, and a
`NavBar` for navigating to new routes: `/dashboard`, `/settings`, and `/send_template`.

The login page posts credentials to the Flask backend and persists the session via cookies.

Custom `error.tsx` and `not-found.tsx` pages handle runtime errors and unknown routes.

Global state is handled with a lightweight Zustand store, and a Next.js rewrite
proxies `/api/*` requests to the Flask backend.

---

## 🗂️ Project Structure

```
/moeen_ai
├── app.py                # Main Flask app
├── tasks.py              # Celery workers for AI and messaging
├── utils.py              # Phone, WhatsApp & email helpers
├── twilio_helpers.py     # Shared Twilio messaging helpers
├── calendar_handlers.py  # Google Calendar event/slot handler
├── llm_utils.py          # GPT-4 assistant runner with tool handlers
├── db.py                 # PostgreSQL connection pool and schema
├── redis_client.py       # Shared Redis client
├── logati.py             # Global logging configuration
├── frontend/             # Next.js client (Glassmorphism Red)
├── templates/            # Legacy HTML frontend (to be replaced by Next.js)
└── requirements.txt      # Dependencies
```

---

## 🚀 Quick Setup

### 1. Clone & Install
```bash
git clone https://github.com/malekalmsaddi/moeen_ai.git
cd moeen_ai
pip install -r requirements.txt
```

### 2. Configure `.env`
```ini
# Twilio
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=
# Optional: messaging service SID (fallback to TWILIO_WHATSAPP_NUMBER if unset)
TWILIO_SERVICE_SID=
TEMPLATE_CONTENT_SID=

# OpenAI
OPENAI_API_KEY=
ASSISTANT_ID=

# Email
SENDGRID_API_KEY=
SENDER_EMAIL=moeen@kulassa.com

# DB & Redis
DATABASE_URL=postgresql://user:pass@localhost/dbname
REDIS_URL=redis://localhost:6379

# Flask
FLASK_SECRET_KEY=
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=  # bcrypt hash of the admin password

# Optional
GOOGLE_CALENDAR_CREDENTIALS_B64=
GOOGLE_CALENDAR_USER=

# Logging
LOG_LEVEL=INFO  # DEBUG for more detail
```

`TWILIO_SERVICE_SID` may be omitted for local development. When unset, messages are sent using `TWILIO_WHATSAPP_NUMBER` directly.

### Frontend Environment

```bash
cp frontend/.env.local.example frontend/.env.local
# edit NEXT_PUBLIC_API_URL in frontend/.env.local; it powers the Next.js rewrite proxying `/api/*` to your Flask backend
```

---

## ▶️ Running Locally

### Start All Components
```bash
# Run Flask app
python app.py

# Run Celery worker
celery -A tasks.celery_app worker --loglevel=info
```

### Start Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

## 🚀 Running with Supervisor
Supervisor lets you keep the app running in the background, auto-restart on crash, and manage logs easily.

1. **Install Supervisor**
   Inside your virtual environment:
   ```bash
   pip install supervisor
   ```
   *(Optional: Silence `pkg_resources` warning)*
   ```bash
   pip install "setuptools<81"
   ```
2. **Create `supervisord.conf` in the project root**
   Example config:
   ```ini
   [supervisord]
   logfile=%(here)s/logs/supervisord.log
   pidfile=%(here)s/supervisord.pid
   childlogdir=%(here)s/logs
   loglevel=info

   [unix_http_server]
   file=%(here)s/supervisor.sock
   chmod=0700

   [rpcinterface:supervisor]
   supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

   [supervisorctl]
   serverurl=unix://%(here)s/supervisor.sock

   [program:moeen]
   directory=%(here)s
   command=%(here)s/venv/bin/python app.py   ; or uvicorn app:app --host 0.0.0.0 --port 8000
   autostart=true
   autorestart=true
   stdout_logfile=%(here)s/logs/moeen.out.log
   stderr_logfile=%(here)s/logs/moeen.err.log
   environment=PYTHONUNBUFFERED="1"
   ```
   Create logs directory:
   ```bash
   mkdir -p logs
   ```
3. **Start Supervisor**
   ```bash
   supervisord -c supervisord.conf
   ```
4. **Managing the Process**
   ```bash
   # Check status
   supervisorctl -c supervisord.conf status

   # Restart app
   supervisorctl -c supervisord.conf restart moeen

   # View logs
   supervisorctl -c supervisord.conf tail -f moeen
   ```
5. **Stop Supervisor**
   ```bash
   supervisorctl -c supervisord.conf stop moeen
   ```
6. **Notes**
   - Adjust `command` for your actual start command.
   - Logs live in `logs/`.
   - `autorestart=true` ensures the process restarts on failure.
   - For production, ensure Supervisor itself is configured to start on system boot.

---

## 🔌 Key Endpoints

| Route | Description |
|-------|-------------|
| `/dashboard` | Admin panel with user conversations |
| `/settings` | Manage notification preferences |
| `/send_template` | Send single or bulk WhatsApp messages |
| `/admin/dashboard` | Advanced admin tools & logs |
| `/metrics` | Prometheus-compatible health stats |
| `/health` | Service heartbeat status |
| `/dashboard/data` | JSON feed for dashboard charts |

---

## 🛠️ User Dashboard Development Tasks

- [x] Gather user requirements and design wireframes
- [x] Implement authentication and session management
- [x] Build a responsive dashboard interface
- [x] Integrate real-time data visualizations
- [x] Add notifications and user settings
- [x] Write tests and update documentation

---


Check for circular imports using:

```bash
pycycle --here
```

Run tests with:

```bash
pytest
# Frontend (when present)
npm test
npm run lint
npm run format
```

---

## 🛡️ Security

- Rate limiting via Redis: 200/day default, stricter per-endpoint
- CSRF tokens enabled on all forms
- bcrypt-hashed admin password
- Session protection: `SameSite`, `HttpOnly`, `Secure`

---

## 📄 License

Apache 2.0 — [Full License](LICENSE)

> Built with 💡 by [Malek Almsaddi](https://github.com/malekalmsaddi) — part of Kulassa's AI Ecosystem.
