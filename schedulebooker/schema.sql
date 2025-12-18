-- schedulebooker/schema.sql

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number  TEXT NOT NULL UNIQUE,
    name          TEXT
);

CREATE TABLE IF NOT EXISTS services (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    duration_min    INTEGER,
    price           REAL
);

CREATE TABLE IF NOT EXISTS appointments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    start_time    TEXT NOT NULL,         -- store ISO string
    notes         TEXT,
    service_id    INTEGER,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,

    FOREIGN KEY(user_id)  REFERENCES users(id),
    FOREIGN KEY(service_id) REFERENCES services(id)
);
