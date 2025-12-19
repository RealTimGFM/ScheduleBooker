# page_contract.md — Sonthien Barbershop Booking App (ScheduleBooker)

This file is the single source of truth for **routes, templates, and form field names**.
Tri (frontend) and Ben (backend) can work in parallel if they follow this contract exactly.

If anything must change, update **this file first**, then update code.

---

## 1) Confirmed requirements (final)
### Time and scheduling
- **Timezone:** Always **Montreal time** (America/Toronto). No timezone selector in UI.
- **Shop hours:** Tue–Sun **11:00–19:00**, closed Monday.
- **Slot grid:** 30-minute steps (11:00, 11:30, 12:00, ...).
- **Service durations:** Variable (e.g., 30/60/90). Duration is chosen by the owner/admin per service.

### Booking rules (Customer / Guest)
- Customers can book **with or without login** (guests allowed).
- Guest booking management: guests search by **phone OR email**.
- **Max 2 bookings/day** per person:
  - If the submitted **phone OR email** already has 2 bookings that day, block the booking.
  - Show message: `If you want more than 2 bookings in a day, contact the barber.`
- Customers/guests can only see **availability**, not other customers.

### Admin rules
- Admin can do **whatever he wants** (no validations).
- Admin can create bookings even if:
  - outside working hours,
  - overlaps other bookings,
  - exceeds max 2/day,
  - **without specifying a barber**.
- Admin can place multiple customers in the same time slot.

### Security recommendation (implemented here)
- Guest **search** by phone/email is allowed.
- Guest **cancel/edit** requires a **booking_code** (prevents random cancellations if someone knows a phone number).

---

## 2) Repo alignment (based on your current project)
- Flask app factory: `schedulebooker/create_app()` in `schedulebooker/__init__.py`
- Existing blueprints:
  - `auth_bp` at `/auth` (phone+name login)
  - `appointments_bp` at `/appointments` (logged-in appointment CRUD)
- Templates live under: `schedulebooker/templates/`
- Static under: `schedulebooker/static/`
- SQLite helpers: `schedulebooker/sqlite_db.py` (`query_db`, `execute_db`)

This contract adds a **public booking flow** and a **basic admin area** (server-rendered, no separate API project).

---

## 3) File ownership (to avoid Git conflicts)
**Tri owns**
- `schedulebooker/templates/public/**`
- `schedulebooker/templates/admin/**`
- `schedulebooker/static/css/**`
- `schedulebooker/static/js/**`
- (Optional) `schedulebooker/templates/base.html` styling only (do not change blocks/variables)

**Ben owns**
- Python routes + helpers
- `schedulebooker/schema.sql`
- `create_db.py`

**Tim owns**
- This contract + merges + final QA checklist

---

## 4) Database fields required (backend)
### Service
- `id`, `name`, `price`, `duration_min`

### Barber (recommended table)
- `id`, `name`, `is_active`

### Booking / Appointment (extend existing appointments table)
Minimum fields needed:
- `id`
- `user_id` (nullable for guests)
- `barber_id` (nullable; admin may omit)
- `service_id`
- `customer_name`
- `customer_phone` (required recommended)
- `customer_email` (optional)
- `start_time` (ISO string)
- `end_time` (ISO string)  ← required for variable durations
- `notes`
- `status` (`booked` / `cancelled`)
- `booking_code` (string)  ← required for secure guest cancel/edit
- `created_at`, `updated_at`

---

## 5) Public pages — routes + templates + form fields

### A) Services list
- **GET** `/services`
- **Template:** `schedulebooker/templates/public/services.html`
- **Context (Ben provides):**
  - `most_popular_services: list[Service]`
  - `other_services: list[Service]`
- **Tri requirements:**
  - Each service row has a **Book** button linking to:
    - `/book?service_id={{ s.id }}`

---

### B) Schedule page (pick barber + date + time)
- **GET** `/book`
- **Query params:**
  - `service_id` (required)
  - `date` (optional; YYYY-MM-DD)
  - `barber_id` (optional; int)
- **Template:** `schedulebooker/templates/public/book_schedule.html`
- **Context (Ben provides):**
  - `service: Service`
  - `barbers: list[Barber]` (active only)
  - `selected_date: str|None`
  - `selected_barber_id: int|None`
  - `time_slots: list[{ "time":"HH:MM", "is_available":bool, "reason":str|None }]`
    - Availability must consider **service.duration_min** and overlaps for that barber.
- **Tri requirements:**
  - User selects `date` and `barber_id` (simple input).
  - Show the times from `time_slots`; disable unavailable ones.

**Form fields (Tri must use exactly):**
- `service_id`
- `barber_id`
- `date`
- `time`

**Submit**
- **POST** `/book/confirm`

---

### C) Confirm page (enter customer info)
- **POST** `/book/confirm`
- **Template:** `schedulebooker/templates/public/book_confirm.html`
- **Context (Ben provides):**
  - `service`, `barber`
  - `date`, `time`
  - `duration_min`
- **Form fields (Tri must use exactly):**
  - hidden: `service_id`, `barber_id`, `date`, `time`
  - `customer_name` (required)
  - `customer_phone` (required recommended)
  - `customer_email` (optional)
  - `notes` (optional)

**Submit**
- **POST** `/book/finish`

---

### D) Finish booking (customer validations happen here)
- **POST** `/book/finish`
- **Backend (Ben):**
  - Validate: not Monday, within 11:00–19:00, 30-min grid, no overlap for barber, max 2/day by phone OR email.
  - Create booking + generate `booking_code`.
  - Redirect to success.

**Redirect**
- `302 → /book/success?booking_id=<id>`

---

### E) Success page
- **GET** `/book/success?booking_id=<id>`
- **Template:** `schedulebooker/templates/public/book_success.html`
- **Context (Ben provides):**
  - `booking` (includes booking_code)
- **Tri requirements:**
  - Show details + booking_code
  - Link to `/find-booking`

---

## 6) Guest find / cancel (secure with booking_code)

### F) Find booking
- **GET** `/find-booking`
- **Template:** `schedulebooker/templates/public/find_booking.html`
- **Form fields:**
  - `contact` (phone OR email)
- **Submit**
  - **POST** `/find-booking`

### G) Find booking results
- **POST** `/find-booking`
- **Template:** `schedulebooker/templates/public/find_booking_results.html`
- **Context (Ben provides):**
  - `contact`
  - `bookings: list[Booking]` (matches phone OR email)
- **Tri requirements:**
  - For each booking, include:
    - input `booking_code`
    - Cancel button posting to cancel endpoint

### H) Cancel booking (requires code)
- **POST** `/booking/<int:booking_id>/cancel`
- **Form fields:**
  - `contact`
  - `booking_code`
- **Backend:**
  - booking must match contact AND booking_code
  - set status to cancelled

---

## 7) Admin area (no validations)

### I) Admin login (default account with hashed password)
- **GET** `/admin/login`
- **POST** `/admin/login`
- **Template:** `schedulebooker/templates/admin/login.html`
- **Fields:**
  - `username`
  - `password`

### J) Admin day view
- **GET** `/admin/day?date=YYYY-MM-DD`
- **Template:** `schedulebooker/templates/admin/day.html`
- **Context:**
  - `date`
  - `bookings` (all bookings for that date)

### K) Admin create booking (NO validations)
- **POST** `/admin/book`
- **Fields:**
  - `customer_name`
  - `customer_phone` (optional)
  - `customer_email` (optional)
  - `service_id`
  - `date`
  - `time`
  - `barber_id` (optional)
- **Behavior:** create booking even if it overlaps or breaks rules.

---

## 8) Templates Tri must create
Public:
- `schedulebooker/templates/public/services.html`
- `schedulebooker/templates/public/book_schedule.html`
- `schedulebooker/templates/public/book_confirm.html`
- `schedulebooker/templates/public/book_success.html`
- `schedulebooker/templates/public/find_booking.html`
- `schedulebooker/templates/public/find_booking_results.html`

Admin:
- `schedulebooker/templates/admin/login.html`
- `schedulebooker/templates/admin/day.html`

---

## 9) Definition of Done (integration)
1) Pages render with real data (Ben)
2) Forms submit successfully (Tri)
3) Customer rules enforced (Ben)
4) Guest cancel requires booking_code (Ben)
5) Admin can create anything (Ben)
