-- schedulebooker/schema.sql
PRAGMA foreign_keys = ON;

-- Users (used by /auth/login phone-based flow)
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number  TEXT NOT NULL UNIQUE,
    name          TEXT
);

-- Services (used by public booking + internal appointments)
CREATE TABLE IF NOT EXISTS services (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,

    category      TEXT NOT NULL DEFAULT 'General',  -- Homme / Femme
    duration_min  INTEGER NOT NULL DEFAULT 30,

    price         REAL NOT NULL DEFAULT 0,
    price_is_from INTEGER NOT NULL DEFAULT 0,       -- 1 means display as "price+"
    price_label   TEXT,                             -- if set, use it instead of price

    is_active     INTEGER NOT NULL DEFAULT 1,
    is_popular    INTEGER NOT NULL DEFAULT 0,
    sort_order    INTEGER NOT NULL DEFAULT 0
);


-- Barbers
CREATE TABLE IF NOT EXISTS barbers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    is_active  INTEGER NOT NULL DEFAULT 1
);

-- Admin users (separate from phone-based users)
CREATE TABLE IF NOT EXISTS admin_users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);

-- Appointments = bookings table (extended)
-- IMPORTANT: keep nullable fields so existing internal inserts won't crash.
CREATE TABLE IF NOT EXISTS appointments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,

    user_id       INTEGER,                 -- now nullable (guest bookings)
    barber_id     INTEGER,                 -- nullable (Any barber)
    service_id    INTEGER,                 -- nullable for old rows, but new bookings should set it

    customer_name  TEXT NOT NULL,
    customer_phone TEXT,
    customer_email TEXT,

    start_time    TEXT NOT NULL,           -- ISO string
    end_time      TEXT,                    -- nullable for old rows (Day 3 will enforce)
    notes         TEXT,

    status        TEXT NOT NULL DEFAULT 'booked' CHECK (status IN ('booked', 'cancelled')),
    booking_code  TEXT UNIQUE,             -- nullable for old rows; new rows should set it

    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,

    FOREIGN KEY(user_id)    REFERENCES users(id),
    FOREIGN KEY(barber_id)  REFERENCES barbers(id),
    FOREIGN KEY(service_id) REFERENCES services(id)
);

CREATE INDEX IF NOT EXISTS idx_appt_start_time ON appointments(start_time);
CREATE INDEX IF NOT EXISTS idx_appt_barber_start ON appointments(barber_id, start_time);
CREATE INDEX IF NOT EXISTS idx_appt_status_start ON appointments(status, start_time);
