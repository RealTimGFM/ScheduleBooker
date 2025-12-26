# ScheduleBooker Developer Playbook (API + Troubleshooting)

This document describes what the ScheduleBooker backend does today:
- Public booking + guest self-service APIs
- Admin APIs
- Business rules
- How to test with `curl` (PowerShell friendly)
- A reusable troubleshooting rule for future issues

> Note: Many routes are server-rendered pages. When templates are missing, the app returns JSON fallback.

---

## Table of Contents
- [1) Run Locally](#1-run-locally)
- [2) Response Format](#2-response-format)
- [3) Key Business Rules](#3-key-business-rules)
- [4) Public Routes](#4-public-routes)
- [5) Guest Self-Service Routes](#5-guest-self-service-routes)
- [6) Admin Routes](#6-admin-routes)
- [7) End-to-End Test Flows (curl)](#7-end-to-end-test-flows-curl)
- [8) Troubleshooting Rule (General)](#8-troubleshooting-rule-general)
- [9) Common Dev Issues](#9-common-dev-issues)
- [10) Where the Code Lives](#10-where-the-code-lives)

---

## 1) Run Locally

### Install dependencies
```powershell
pip install -r requirements.txt
Initialize DB (schema + seed)
Your repo uses a DB init script (commonly):

powershell
Copy code
python .\create_db.py
Start the server
powershell
Copy code
python .\app.py
Default dev URL:

http://127.0.0.1:5000

2) Response Format
Most routes use render_or_json(...):

If the matching Jinja template exists → HTML is returned.

If the template is missing → JSON fallback is returned:

json
Copy code
{
  "template": "some/template.html",
  "context": { ... }
}
This makes it possible to test backend routes via curl before frontend pages exist.

3) Key Business Rules
Public booking flow rules (enforced on public routes)
These rules apply to public booking endpoints:

Closed Mondays

Shop hours (Tue–Sun): 11:00 → 19:00

Slot grid: 30-minute increments (HH:00 / HH:30)

Overlap prevention:

Same barber cannot have overlapping appointments.

If barber is not selected, availability can be “any barber free.”

Shop capacity per slot:

SHOP_CAPACITY_PER_SLOT exists (default 3).

Effective cap is limited by number of active barbers.

Max 2 bookings/day per customer by phone OR email

3rd attempt returns:

"If you want more than 2 bookings in a day, contact the barber."

Admin create booking rules (NOT enforced)
Admin can create bookings with NO validations:

Can overlap

Can be outside hours

Can be on Monday

barber_id can be omitted

4) Public Routes
GET /services
Purpose:

Lists active services.

Often returns context split into:

most_popular_services

other_services

Test:

powershell
Copy code
curl.exe -s "http://127.0.0.1:5000/services" | python -m json.tool
GET /book?service_id=1&date=YYYY-MM-DD&barber_id=1
Purpose:

Returns availability grid for a service duration on a given date.

Inputs:

service_id (required)

date (optional; defaults to today)

barber_id (optional)

Context includes:

service

barbers

selected_date

selected_barber_id

time_slots[]:

{ "time": "17:30", "is_available": true, "reason": null }

Test:

powershell
Copy code
curl.exe -s "http://127.0.0.1:5000/book?service_id=1&date=2025-12-24&barber_id=1" | python -m json.tool
POST /book/confirm (no DB write)
Purpose:

Confirmation step before writing to DB.

Form fields:

service_id

barber_id

date (YYYY-MM-DD)

time (HH:MM)

Test:

powershell
Copy code
curl.exe -s -X POST "http://127.0.0.1:5000/book/confirm" `
  -d "service_id=1" `
  -d "barber_id=1" `
  -d "date=2025-12-24" `
  -d "time=17:30" | python -m json.tool
POST /book/finish (DB write)
Purpose:

Creates an appointment if valid per public rules.

Success: 302 redirect → /book/success?booking_id=<id>

Failure: 200 with error in context

Form fields:

service_id (required)

barber_id (required)

date (required)

time (required)

customer_name (required)

customer_phone (commonly required in current flow/tests)

customer_email (optional)

notes (optional)

Test (shows redirect + booking_id):

powershell
Copy code
curl.exe -s -i -X POST "http://127.0.0.1:5000/book/finish" `
  -d "service_id=1" `
  -d "barber_id=1" `
  -d "date=2025-12-24" `
  -d "time=17:30" `
  -d "customer_name=Demo Guest" `
  -d "customer_phone=9025550007" `
  -d "customer_email=demo@example.com" `
  -d "notes=demo"
Common failures:

Monday:

"Closed (Monday)"

Slot taken / overlap:

"That time is no longer available. Please choose another slot."

Max 2/day:

"If you want more than 2 bookings in a day, contact the barber."

GET /book/success?booking_id=<id>
Purpose:

Booking confirmation summary.

Context typically includes booking with booking_code.

If not found:

"Booking not found."

Test:

powershell
Copy code
curl.exe -s "http://127.0.0.1:5000/book/success?booking_id=1" | python -m json.tool
5) Guest Self-Service Routes
GET /find-booking
Purpose:

Shows “find booking” form.

POST /find-booking
Purpose:

Finds bookings by:

phone (digits normalized) OR

email (case-insensitive)

Form fields:

contact

Test:

powershell
Copy code
curl.exe -s -X POST "http://127.0.0.1:5000/find-booking" `
  -d "contact=9025550007" | python -m json.tool
POST /booking/<booking_id>/cancel
Purpose:

Guest cancellation requires BOTH:

correct contact

correct booking_code

Success sets status='cancelled'

Form fields:

contact

booking_code

Test:

powershell
Copy code
curl.exe -s -i -X POST "http://127.0.0.1:5000/booking/1/cancel" `
  -d "contact=9025550007" `
  -d "booking_code=PASTE_CODE_HERE"
6) Admin Routes
Admin auth uses session cookies:

Table: admin_users(id, username, password_hash)

Session key: admin_user_id

GET /admin/login
Purpose:

Admin login page.

POST /admin/login
Purpose:

Verify username/password hash.

On success:

sets session cookie

redirects to /admin/day

Form fields:

username

password

Test (store cookie jar):

powershell
Copy code
curl.exe -i -c admin_cookies.txt -X POST "http://127.0.0.1:5000/admin/login" `
  -d "username=T" `
  -d "password=1"
GET /admin/day?date=YYYY-MM-DD
Purpose:

Lists all bookings for that date.

Test:

powershell
Copy code
curl.exe -s -b admin_cookies.txt "http://127.0.0.1:5000/admin/day?date=2025-12-24" | python -m json.tool
POST /admin/book (NO validations)
Purpose:

Create a booking regardless of public constraints.

Required:

customer_name

service_id

date

time

Optional:

customer_phone

customer_email

barber_id

Test:

powershell
Copy code
curl.exe -i -b admin_cookies.txt -X POST "http://127.0.0.1:5000/admin/book" `
  -d "customer_name=Admin Demo" `
  -d "service_id=1" `
  -d "date=2025-12-22" `
  -d "time=02:00"
7) End-to-End Test Flows (curl)
Flow A: Public booking
Check availability:

powershell
Copy code
curl.exe -s "http://127.0.0.1:5000/book?service_id=1&date=2025-12-24&barber_id=1" | python -m json.tool
Finish booking (expect 302 + booking_id in Location):

powershell
Copy code
curl.exe -s -i -X POST "http://127.0.0.1:5000/book/finish" `
  -d "service_id=1" `
  -d "barber_id=1" `
  -d "date=2025-12-24" `
  -d "time=18:00" `
  -d "customer_name=E2E Guest" `
  -d "customer_phone=9025550007"
Flow B: Find + cancel
Find:

powershell
Copy code
curl.exe -s -X POST "http://127.0.0.1:5000/find-booking" `
  -d "contact=9025550007" | python -m json.tool
Cancel (requires booking_code):

powershell
Copy code
curl.exe -s -i -X POST "http://127.0.0.1:5000/booking/BOOKING_ID/cancel" `
  -d "contact=9025550007" `
  -d "booking_code=PASTE_CODE_HERE"
Flow C: Admin
Login:

powershell
Copy code
curl.exe -i -c admin_cookies.txt -X POST "http://127.0.0.1:5000/admin/login" `
  -d "username=T" `
  -d "password=1"
Create booking (no validations):

powershell
Copy code
curl.exe -i -b admin_cookies.txt -X POST "http://127.0.0.1:5000/admin/book" `
  -d "customer_name=Admin E2E" `
  -d "service_id=1" `
  -d "date=2025-12-24" `
  -d "time=02:00"
View day:

powershell
Copy code
curl.exe -s -b admin_cookies.txt "http://127.0.0.1:5000/admin/day?date=2025-12-24" | python -m json.tool
8) Troubleshooting Rule (General)
Troubleshooting Rule: Pin the Failing Command + Classify the Failure (Tool / Policy / Runtime)
Goal: Cut troubleshooting time by identifying the exact failure layer before changing code.

Step 0 — Pin the exact failure

Copy the exact command that failed (from CI logs or terminal).

Copy the first error line (the one that explains what, not the stack trace noise).

Step 1 — Reproduce locally using the same interpreter (avoid PATH traps)
Run tools via Python module form:

python -m <tool> <args>

Examples:

python -m ruff check .

python -m ruff format --check .

python -m pytest

Step 2 — Classify the failure into ONE category
A) Tool/Environment failure (tool can’t run)
Signs:

command not found

module not found

wrong version
Fix:

install tool in the active environment

run via python -m ...

verify: python -m <tool> --version

B) Policy failure (tool runs, but rules fail)
Signs:

would reformat…

lint violations…

assertion failed…
Fix:

apply the policy fix command (e.g., python -m ruff format .)

rerun the exact check command

C) Runtime failure (app/code crashes)
Signs:

traceback, exceptions, DB errors, missing columns/config
Fix:

reproduce minimal case

inspect logs/traceback

fix code/schema/config

Step 3 — Apply the minimal fix, then re-run the same command
Rule: don’t fix multiple things at once.

Make one change

Re-run the exact failing command

Confirm the error changes or disappears

Step 4 — If local passes but CI fails: check mismatch
Compare:

Python version

dependency versions

OS differences

CI commands vs local commands

What to paste to GPT next time

exact failing command

first ~20 lines of error output

OS + Python version

whether python -m <tool> --version works

9) Common Dev Issues
JSON parse error: Expecting value: line 1 column 1
This happens when you pipe HTML into python -m json.tool.
Fix:

Add -i to view headers

Remove | python -m json.tool if response is HTML

Use -L to follow redirects

Getting booking_id from /book/finish
Use curl -i and read the Location header:

/book/success?booking_id=<id>

Admin route redirects back to login
You forgot to send cookies:

Save cookies: -c admin_cookies.txt

Send cookies: -b admin_cookies.txt

Ruff commands (Windows-safe)
Lint:

python -m ruff check .

Format check:

python -m ruff format --check .

Apply formatting:

python -m ruff format .

10) Where the Code Lives
Public booking logic & time slots:

schedulebooker/public/routes.py

Admin auth/day/create:

schedulebooker/admin/routes.py

DB helpers:

schedulebooker/sqlite_db.py

DB schema + seed:

schedulebooker/schema.sql

create_db.py (or equivalent init script)

sql
Copy code

```powershell
git add docs/Developer_Playbook.md
git commit -m "Add developer playbook (API + troubleshooting)"