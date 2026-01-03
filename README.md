# ScheduleBooker

ScheduleBooker is a simple schedule/appointment booking web app for a barber shop. It’s designed to let you log in and manage bookings in one place.

## What you can do

- Log in / Log out
- View appointments
- Create a new appointment
- Edit an existing appointment
- Pick a service when creating/editing an appointment (services are stored in the database)

## How it works (simple)

- You open the site, log in, and then you can manage appointments.
- All appointment data is saved in a database so it stays there after you refresh.

## Run it locally (quick start)

1) Clone the repo
```bash
git clone https://github.com/RealTimGFM/ScheduleBooker.git
cd ScheduleBooker
```

2) Install requirements
```bash
pip install -r requirements.txt
```

3) Create/initialize the database
```bash
python create_db.py
```

4) Start the app
```bash
python app.py
```

5) Open in your browser:
- http://127.0.0.1:5000

## Deploy on Render (simple)

This repo includes files to help deploy on Render.

Typical steps:
1. Create a new Web Service on Render from this GitHub repo
2. Add a Render database (PostgreSQL)
3. Add the app environment variables on Render (example: database connection)
4. Deploy

## Automatic bug checking on GitHub

This project includes GitHub Actions that automatically run checks when code is pushed when code is pushed to GitHub (format/lint + tests). If something breaks, GitHub shows a red X so it’s easy to notice early.

## Notes

- If you’re running locally, you can start with the default setup.
- For hosting, connect it to a real database (like PostgreSQL) so data is stable long-term.

### Email Configuration (EmailJS)

This app uses EmailJS for password reset emails.

#### Setup:
1. Create free account at https://www.emailjs.com/
2. Add an email service (Gmail recommended)
3. Create email template with these variables:
   - `{{to_email}}` - Recipient email
   - `{{to_name}}` - Admin username
   - `{{reset_url}}` - Password reset link
4. Copy your credentials to `.env`:
```
   EMAILJS_PUBLIC_KEY=your_key
   EMAILJS_SERVICE_ID=your_service
   EMAILJS_TEMPLATE_ID=your_template
```

#### Development Mode:
- Reset emails are logged to console
- Copy the reset URL from console logs
- No actual emails are sent

#### Production Mode:
- Configure EmailJS credentials in `.env`
- Emails are sent via EmailJS API
- Rate limited to prevent abuse

## Members
- TimGFM
- TriBo
- Chunkyboi

## How to fix lint-format
```bash
ruff check . --fix
ruff format .
pytest -q
```