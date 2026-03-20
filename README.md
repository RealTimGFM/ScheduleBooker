# ScheduleBooker

ScheduleBooker is a Flask appointment-booking app for a barbershop. It keeps the current server-rendered website working while moving toward a cleaner backend structure that can support future `/api/v1/...` endpoints and mobile clients.

The app currently includes:

- a public booking flow
- guest booking lookup and cancellation
- a customer appointments area
- an admin panel
- a small reusable service/repository layer
- a real `/api/v1` namespace for read-only API access

## What the app does

### Public / guest features

- Browse active services
- View availability by date and barber
- Book appointments through a confirm and finish flow
- Find bookings by phone or email
- Cancel a booking with contact info and booking code

### Customer account features

- Sign up with phone + PIN
- Log in with phone + PIN
- View personal appointments
- Create, edit, and delete personal appointments

### Admin features

- Admin login and session-based access
- Day calendar view
- Create, edit, and delete bookings
- Service management
- Barber management
- Income report view
- Admin profile and password management
- Password reset flow with EmailJS support

## Current architecture

This project stays as one Flask repo and keeps the app factory pattern.

### Backend structure

```text
schedulebooker/
  __init__.py
  admin/
  api/
    v1/
  appointments/
  auth/
  public/
  repositories/
  services/
  static/
  templates/
  schema.sql
  schema_postgres.sql
  sqlite_db.py
```

### Design direction

- Web routes remain in blueprints
- Shared booking rules live in `schedulebooker/services/`
- Raw database queries are being moved into `schedulebooker/repositories/`
- SQLite is the default local database
- PostgreSQL is supported through `DATABASE_URL`

This keeps the current website simple while making future API/mobile work easier.

## Main blueprints

- `public` for guest-facing pages
- `auth` for customer login/signup
- `appointments` for logged-in customer appointments
- `admin` for back-office tools
- `api_v1` for `/api/v1/...`

## Tech stack

- Python
- Flask
- SQLite for local development
- PostgreSQL support through `psycopg2`
- HTML, CSS, JavaScript
- pytest
- ruff
- python-dotenv
- EmailJS for admin password reset emails

## Booking rules

- App timezone: `America/Toronto`
- Shop hours: Tuesday to Sunday, `11:00` to `19:00`
- Monday is closed
- Time grid uses 30-minute slots
- Shop capacity is limited per 30-minute segment
- Public bookings cannot be created in the past
- Customer cancellations are blocked within 30 minutes of start time

## Local setup

### 1. Create a virtual environment

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialize the database

```bash
python create_db.py
```

This will:

- create the schema
- seed starter services
- seed starter barbers
- create a default admin account

### 4. Run the app

```bash
python app.py
```

### 5. Open it in the browser

- Public site: `http://127.0.0.1:5000/services`
- Customer login: `http://127.0.0.1:5000/auth/login`
- Admin login: `http://127.0.0.1:5000/admin/login`

Note: the root route `/` redirects to the customer appointments area, so `/services` is the public entry point.

## Default local admin account

`create_db.py` seeds this default admin account if no admin exists yet:

- Username: `T`
- Password: `1`

Change it after first login.

## Database notes

### SQLite

- Default local DB path: `instance/appointments.db`
- Good for local development and small deployments

### PostgreSQL

PostgreSQL is supported through `DATABASE_URL`.

- `sqlite_db.py` switches backend based on `DATABASE_URL`
- `create_db.py` uses `schema_postgres.sql` when PostgreSQL is configured

This keeps local development simple while preserving a production migration path.

## API v1 endpoints

The app now includes a small real API namespace under `/api/v1`.

Current endpoints:

- `GET /api/v1/health`
- `GET /api/v1/services`
- `GET /api/v1/barbers`
- `GET /api/v1/availability?service_id=...&date=YYYY-MM-DD&barber_id=...`

These endpoints reuse existing repository/service logic rather than duplicating business rules.

## Testing

Run the test suite with:

```bash
pytest -q
```

The repo also includes a local pytest configuration so tests collect only from `tests/` and use a workspace-local temp directory.

## Linting

```bash
python -m ruff check .
```

## EmailJS configuration

EmailJS is used for admin password reset emails.

Add these values to `.env`:

```env
EMAILJS_PUBLIC_KEY=your_key
EMAILJS_SERVICE_ID=your_service
EMAILJS_TEMPLATE_ID=your_template
APP_BASE_URL=http://127.0.0.1:5000
```

Expected template variables:

- `to_email`
- `to_name`
- `reset_url`

## Deployment

This repo includes:

- `render.yaml`
- `start.sh`
- `wsgi.py`

Typical Render flow:

1. Connect the repo to Render
2. Install with `pip install -r requirements.txt`
3. Start with `./start.sh`
4. Set environment variables such as `SECRET_KEY` and optionally `DATABASE_URL`

For real production use, PostgreSQL is the better long-term choice.

## Current status

The codebase already matches several important architectural goals:

- one Flask repo
- app factory pattern
- blueprint-based web structure
- shared booking service logic
- repository layer started
- real `/api/v1` namespace
- SQLite local support with PostgreSQL direction preserved

The main area still worth refactoring later is `schedulebooker/admin/routes.py`, which is still large and owns a lot of direct SQL and business logic.

## Team

- TimGFM
- TriBo
- Chunkyboi

## How to fix lint-format

```bash
python -m ruff check . --fix
python -m ruff format .
pytest -q
```
