# ScheduleBooker

ScheduleBooker is a simple barbershop scheduling app built with **Flask + SQLite**.

It has:
- A **public booking flow** (browse services → pick a time slot → confirm → finish).
- **Guest self-service** (find bookings + cancel using a booking code).
- A lightweight **admin panel** (day calendar + manage services + manage barbers + settings).

> Note: The app timezone is **America/Toronto (Montreal)** and shop hours are **Tue–Sun 11:00–19:00** (closed Monday). Slot grid is **30 minutes**.

---

## About this project

This project was created to give a barbershop a clean, simple scheduling system:
- Customers can book quickly without needing accounts.
- Admin can manage the schedule and business data (services, barbers) in one place.
- Built with a “keep it simple” approach: server-rendered pages, SQLite database, and minimal moving parts.

---

## Technologies used

- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, JavaScript (server-rendered templates)
- **Database:** SQLite (stored under the `instance/` folder by default)
- **Tooling:** pytest, ruff
- **Deploy:** Render (AWS EC2 in the future)

---

## What you can do (features)

### Customer / Guest (Public)
- Browse services (categorized, priced, duration-based).
- Pick a service and view available time slots for a date.
- Book an appointment (two-step flow: confirm → finish).
- Get a **booking code** after booking (used for guest self-service).
- Find bookings using **phone OR email**.
- Cancel a booking (guest cancellation requires **booking_code** for security).

### Admin (Back Office)
- Login and view the **day calendar**.
- Create bookings directly from the calendar.
- Manage **services** (create/edit/activate/deactivate).
- Manage **barbers** (create/edit/activate/deactivate).
- Admin settings:
  - Update profile information (requires current password).
  - Change password (min 8 chars).
  - Forgot password via Email (link) or SMS (code).

---

## How it works (simple)

### Public booking flow
1) Customer opens the public site and chooses a service.
2) Customer selects a date and a time slot (30-min grid).
3) App shows a **confirm** step (no DB write yet).
4) On “Finish”, the booking is saved and a **booking code** is generated.

### Guest self-service
- Guests can search bookings with **phone OR email**.
- Guests can only cancel/edit when they provide the correct **booking_code** (prevents random cancellations if someone knows a phone number).

### Database
- App uses SQLite and stores the DB file in `instance/appointments.db` by default.
- The root route `/` redirects to the internal appointments list; the public entry point is `/services`.

---

## Run it locally

### 1) Create a virtual environment + install dependencies
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2) Initialize the database (schema + seed data)
```bash
python create_db.py
```
This runs `schedulebooker/schema.sql` and seeds initial services (and other starter data).

### 3) Run the app
```bash
python app.py
```
App will run in debug mode locally.

### 4) Open the app
- Public: `http://127.0.0.1:5000/services`
- Admin:  `http://127.0.0.1:5000/admin/login`

### Default admin credentials (local seed)
- Username: `T`
- Password: `1`

(You should change the password in Admin Settings after first login.)

---

## Deploy on Render

This repo includes a Render blueprint:
- `render.yaml`
- `start.sh` (Gunicorn start)

### Typical steps
1) Create a new **Web Service** on Render and connect this GitHub repo.
2) Render should auto-detect `render.yaml`. If not, set:
   - Build command: `pip install -r requirements.txt`
   - Start command: `./start.sh`

### Important note about SQLite on hosting
SQLite is fine for local dev and demos. For real production usage, you should use:
- A persistent disk (so the SQLite file isn’t lost on redeploy), or
- A real hosted database like PostgreSQL (recommended long-term).

---

## Automatic bug checking on GitHub

A GitHub Actions workflow runs on push/PR to keep the project clean:
- Ruff lint check + format check
- Pytest test suite
- Basic dependency security audit

---

## Notes

- Timezone is fixed to Montreal time (America/Toronto).
- Slot grid is 30 minutes (11:00, 11:30, 12:00, ...).
- Guest self-service is intentionally protected by booking_code to prevent abuse.
- If you want “real hosting” stability, plan a migration to PostgreSQL later.

---

## Email Configuration (EmailJS)

This app uses **EmailJS** for **admin password reset emails**.

### Setup:
1) Create a free account at https://www.emailjs.com/
2) Add an email service (Gmail recommended)
3) Create an email template with these variables:
   - `{{to_email}}` — recipient email
   - `{{to_name}}` — admin username
   - `{{reset_url}}` — password reset link
4) Add credentials to `.env`:
```env
EMAILJS_PUBLIC_KEY=your_key
EMAILJS_SERVICE_ID=your_service
EMAILJS_TEMPLATE_ID=your_template
```

### Development mode
- Reset links are logged to console (no real email is sent).

### Production mode
- Configure EmailJS keys in `.env`
- Emails are sent via EmailJS
- Rate limiting is enabled to reduce abuse

---

## Future improvements

- Switch from SQLite to PostgreSQL for production stability.
- Better analytics / reporting (daily totals, barber performance, etc.).
- Better admin calendar UX (drag/drop, resizing, conflict highlighting).

---

## Members
- TimGFM
- TriBo
- Chunkyboi

---

## How to fix lint-format

```bash
python -m ruff check . --fix
python -m ruff format .
pytest -q
```
