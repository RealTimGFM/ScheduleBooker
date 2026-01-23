-- schedulebooker/schema_postgres.sql

-- USERS
CREATE TABLE IF NOT EXISTS users (
  id            SERIAL PRIMARY KEY,
  phone_number  TEXT NOT NULL UNIQUE,
  name          TEXT,
  password_hash TEXT
);

-- SERVICES
CREATE TABLE IF NOT EXISTS services (
  id            SERIAL PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,

  category      TEXT    NOT NULL DEFAULT 'General',
  duration_min  INTEGER NOT NULL DEFAULT 30,

  price         DOUBLE PRECISION NOT NULL DEFAULT 0,
  price_is_from INTEGER NOT NULL DEFAULT 0,
  price_label   TEXT,

  is_active     INTEGER NOT NULL DEFAULT 1,
  is_popular    INTEGER NOT NULL DEFAULT 0,
  sort_order    INTEGER NOT NULL DEFAULT 0
);

-- BARBERS
CREATE TABLE IF NOT EXISTS barbers (
  id        SERIAL PRIMARY KEY,
  name      TEXT    NOT NULL UNIQUE,
  phone     TEXT    NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1
);

-- ADMIN USERS
CREATE TABLE IF NOT EXISTS admin_users (
  id            SERIAL PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  email         TEXT,
  phone         TEXT
);

-- APPOINTMENTS
CREATE TABLE IF NOT EXISTS appointments (
  id             SERIAL PRIMARY KEY,

  user_id        INTEGER,
  barber_id      INTEGER,
  service_id     INTEGER,

  customer_name  TEXT NOT NULL,
  customer_phone TEXT,
  customer_email TEXT,

  start_time     TEXT NOT NULL,
  end_time       TEXT,
  notes          TEXT,

  status         TEXT NOT NULL DEFAULT 'booked'
               CHECK (status IN ('booked', 'cancelled')),
  booking_code   TEXT UNIQUE,

  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL,

  FOREIGN KEY (user_id)    REFERENCES users(id),
  FOREIGN KEY (barber_id)  REFERENCES barbers(id),
  FOREIGN KEY (service_id) REFERENCES services(id)
);

-- ADMIN PASSWORD RESETS
CREATE TABLE IF NOT EXISTS admin_password_resets (
  id            SERIAL PRIMARY KEY,
  admin_user_id INTEGER NOT NULL,
  token_hash    TEXT NOT NULL UNIQUE,
  channel       TEXT NOT NULL CHECK (channel IN ('email', 'sms')),
  expires_at    TEXT NOT NULL,
  used_at       TEXT,
  attempts      INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL,
  FOREIGN KEY (admin_user_id) REFERENCES admin_users(id)
);

-- ADMIN RESET RATE LIMITS
CREATE TABLE IF NOT EXISTS admin_reset_rate_limits (
  id            SERIAL PRIMARY KEY,
  admin_user_id INTEGER NOT NULL,
  channel       TEXT NOT NULL CHECK (channel IN ('email', 'sms')),
  last_sent_at  TEXT NOT NULL,
  FOREIGN KEY (admin_user_id) REFERENCES admin_users(id)
);

-- CANCELLATIONS (kept independent of appointments FK to preserve history)
CREATE TABLE IF NOT EXISTS cancellations (
  id                SERIAL PRIMARY KEY,
  booking_id        INTEGER NOT NULL,
  customer_name     TEXT NOT NULL,
  customer_phone    TEXT,
  customer_email    TEXT,
  barber_id         INTEGER,
  barber_name       TEXT,
  service_id        INTEGER,
  service_name      TEXT,
  start_datetime    TEXT NOT NULL,
  end_datetime      TEXT,
  cancelled_at      TEXT NOT NULL,
  cancelled_by      TEXT NOT NULL CHECK (cancelled_by IN ('customer', 'admin')),

  FOREIGN KEY (barber_id)  REFERENCES barbers(id),
  FOREIGN KEY (service_id) REFERENCES services(id)
);
