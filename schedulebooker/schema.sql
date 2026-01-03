-- schedulebooker/schema.sql
PRAGMA foreign_keys = ON;

-- ============================================================
-- USERS (used by /auth/login phone-based flow)
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  phone_number  TEXT NOT NULL UNIQUE,
  name          TEXT,
  password_hash TEXT
);

-- ============================================================
-- SERVICES (used by public booking + internal appointments)
-- ============================================================
CREATE TABLE IF NOT EXISTS services (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL UNIQUE,

  category      TEXT    NOT NULL DEFAULT 'General',  -- Homme / Femme
  duration_min  INTEGER NOT NULL DEFAULT 30,

  price         REAL    NOT NULL DEFAULT 0,
  price_is_from INTEGER NOT NULL DEFAULT 0,          -- 1 means display as "price+"
  price_label   TEXT,                                -- if set, use it instead of price

  is_active     INTEGER NOT NULL DEFAULT 1,
  is_popular    INTEGER NOT NULL DEFAULT 0,
  sort_order    INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- BARBERS
-- ============================================================
CREATE TABLE IF NOT EXISTS barbers (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  name      TEXT    NOT NULL UNIQUE,
  phone     TEXT    NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- ADMIN USERS (separate from phone-based users)
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL
);

-- ============================================================
-- APPOINTMENTS = bookings table (extended)
-- IMPORTANT: keep nullable fields so existing internal inserts won't crash.
-- ============================================================
CREATE TABLE IF NOT EXISTS appointments (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,

  user_id        INTEGER,  -- now nullable (guest bookings)
  barber_id      INTEGER,  -- nullable (Any barber)
  service_id     INTEGER,  -- nullable for old rows, but new bookings should set it

  customer_name  TEXT NOT NULL,
  customer_phone TEXT,
  customer_email TEXT,

  start_time     TEXT NOT NULL,  -- ISO string
  end_time       TEXT,           -- nullable for old rows (Day 3 will enforce)
  notes          TEXT,

  status         TEXT NOT NULL DEFAULT 'booked' CHECK (status IN ('booked', 'cancelled')),
  booking_code   TEXT UNIQUE,    -- nullable for old rows; new rows should set it

  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL,

  FOREIGN KEY (user_id)    REFERENCES users(id),
  FOREIGN KEY (barber_id)  REFERENCES barbers(id),
  FOREIGN KEY (service_id) REFERENCES services(id)
);

CREATE INDEX IF NOT EXISTS idx_appt_start_time    ON appointments(start_time);
CREATE INDEX IF NOT EXISTS idx_appt_barber_start  ON appointments(barber_id, start_time);
CREATE INDEX IF NOT EXISTS idx_appt_status_start  ON appointments(status, start_time);

-- ============================================================
-- Extend admin_users table (add columns if not exist)
-- These will be added via migration function in sqlite_db.py
-- ============================================================

-- ============================================================
-- PASSWORD RESET TOKENS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_password_resets (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  admin_user_id INTEGER NOT NULL,
  token_hash    TEXT NOT NULL UNIQUE,
  channel       TEXT NOT NULL CHECK (channel IN ('email', 'sms')),
  expires_at    TEXT NOT NULL,
  used_at       TEXT,
  attempts      INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL,
  FOREIGN KEY (admin_user_id) REFERENCES admin_users(id)
);

CREATE INDEX IF NOT EXISTS idx_reset_token   ON admin_password_resets(token_hash);
CREATE INDEX IF NOT EXISTS idx_reset_expires ON admin_password_resets(expires_at);

-- ============================================================
-- RATE LIMITING TABLE FOR PASSWORD RESET SENDS
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_reset_rate_limits (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  admin_user_id INTEGER NOT NULL,
  channel       TEXT NOT NULL CHECK (channel IN ('email', 'sms')),
  last_sent_at  TEXT NOT NULL,
  FOREIGN KEY (admin_user_id) REFERENCES admin_users(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rate_limit_admin_channel
  ON admin_reset_rate_limits(admin_user_id, channel);
