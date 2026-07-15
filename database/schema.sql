-- Smart Classroom Attendance System — reference schema (SQLite dialect).
--
-- The application creates these tables automatically via SQLAlchemy
-- (db.create_all / `flask init-db`); this file documents the schema and can
-- be used to create the database by hand:  sqlite3 attendance.db < schema.sql
--
-- PostgreSQL migration notes:
--   INTEGER PRIMARY KEY  -> SERIAL/IDENTITY
--   BLOB                 -> BYTEA
--   Everything else is portable.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      VARCHAR(64)  NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,          -- werkzeug scrypt/pbkdf2 hash
    role          VARCHAR(16)  NOT NULL DEFAULT 'teacher',  -- 'admin' | 'teacher'
    created_at    DATETIME
);

CREATE TABLE IF NOT EXISTS students (
    student_id    INTEGER PRIMARY KEY,
    full_name     VARCHAR(120) NOT NULL,
    roll_number   VARCHAR(32)  NOT NULL UNIQUE,
    department    VARCHAR(80)  NOT NULL,
    year          INTEGER      NOT NULL,
    face_encoding BLOB,                            -- numpy .npy: float64 (n, 128)
    created_at    DATETIME,
    updated_at    DATETIME
);

CREATE TABLE IF NOT EXISTS attendance (
    attendance_id    INTEGER PRIMARY KEY,
    student_id       INTEGER NOT NULL REFERENCES students(student_id),
    date             DATE    NOT NULL,
    time             TIME    NOT NULL,
    status           VARCHAR(16) NOT NULL,          -- 'Present' | 'Late'
    confidence_score FLOAT,                        -- NULL for manual entries
    -- The duplicate-prevention guarantee: one row per student per day.
    CONSTRAINT uq_attendance_student_date UNIQUE (student_id, date)
);

CREATE INDEX IF NOT EXISTS ix_users_username      ON users (username);
CREATE INDEX IF NOT EXISTS ix_students_roll       ON students (roll_number);
CREATE INDEX IF NOT EXISTS ix_attendance_student  ON attendance (student_id);
CREATE INDEX IF NOT EXISTS ix_attendance_date     ON attendance (date);
