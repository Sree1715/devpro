import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_db_path() -> str:
    """Resolve DB_PATH environment variable to an absolute path."""
    env_path = os.getenv("DB_PATH", "smart_manure/app.db").strip()
    if os.path.isabs(env_path):
        resolved = env_path
    else:
        if env_path.startswith("smart_manure/") or env_path.startswith("smart_manure\\"):
            relative_sub = env_path[len("smart_manure/"):].lstrip("\\/")
            resolved = os.path.join(BASE_DIR, relative_sub)
        else:
            resolved = os.path.join(BASE_DIR, env_path)
    resolved = os.path.abspath(resolved)
    try:
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
    except Exception:
        pass
    return resolved

def get_connection():
    """Returns a SQLite connection with foreign keys enabled, WAL journal mode, and Row factory."""
    try:
        db_file = get_db_path()
        conn = sqlite3.connect(db_file, check_same_thread=False, timeout=15.0)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        raise RuntimeError(f"Database connection error: {e}")

def init_db():
    """Initializes the SQLite database schema with foreign keys turned on."""
    conn = get_connection()
    try:
        with conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('FARMER', 'AUTHORITY')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_name TEXT NOT NULL,
                owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                api_key_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, device_name)
            );

            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                temperature_c REAL NOT NULL,
                moisture_percent REAL NOT NULL,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS manure_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_code TEXT UNIQUE NOT NULL,
                farmer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                reading_id INTEGER REFERENCES readings(id) ON DELETE SET NULL,
                temperature_c REAL NOT NULL,
                moisture_percent REAL NOT NULL,
                nitrogen REAL NOT NULL,
                phosphorus REAL NOT NULL,
                potassium REAL NOT NULL,
                soil_type TEXT NOT NULL,
                preferred_crop TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'APPROVED', 'REJECTED')),
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMP,
                review_note TEXT
            );

            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id INTEGER UNIQUE NOT NULL REFERENCES manure_samples(id) ON DELETE CASCADE,
                top1_crop TEXT NOT NULL,
                top2_crop TEXT NOT NULL,
                model_version TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id INTEGER NOT NULL REFERENCES manure_samples(id) ON DELETE CASCADE,
                prediction_id INTEGER NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
                farmer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                pdf_blob BLOB NOT NULL,
                delivery_status TEXT NOT NULL DEFAULT 'NOT_SENT' CHECK(delivery_status IN ('NOT_SENT', 'DELIVERED_IN_APP')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                delivered_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                farmer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                report_id INTEGER REFERENCES reports(id) ON DELETE SET NULL,
                message TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
    finally:
        conn.close()

# ----------------- USERS -----------------
def get_user_by_email(email: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
        return cursor.fetchone()
    finally:
        conn.close()

def get_user_by_id(user_id: int):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cursor.fetchone()
    finally:
        conn.close()

def create_user(name: str, email: str, phone: Optional[str], password_hash: str, role: str) -> int:
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (name, email, phone, password_hash, role)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name.strip(), email.strip().lower(), phone.strip() if phone else None, password_hash, role)
            )
            return cursor.lastrowid
    finally:
        conn.close()

# ----------------- DEVICES -----------------
def create_device(owner_id: int, device_name: str, api_key_hash: str) -> int:
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO devices (device_name, owner_id, api_key_hash)
                VALUES (?, ?, ?)
                """,
                (device_name.strip(), owner_id, api_key_hash)
            )
            return cursor.lastrowid
    finally:
        conn.close()

def get_devices_for_owner(owner_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM devices WHERE owner_id = ? ORDER BY created_at DESC",
            (owner_id,)
        )
        return cursor.fetchall()
    finally:
        conn.close()

def get_device_by_id(device_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
        return cursor.fetchone()
    finally:
        conn.close()

def get_all_devices() -> List[sqlite3.Row]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices ORDER BY id ASC")
        return cursor.fetchall()
    finally:
        conn.close()

# ----------------- READINGS -----------------
def insert_reading(device_id: int, temperature_c: float, moisture_percent: float) -> int:
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO readings (device_id, temperature_c, moisture_percent)
                VALUES (?, ?, ?)
                """,
                (device_id, round(float(temperature_c), 2), round(float(moisture_percent), 2))
            )
            return cursor.lastrowid
    finally:
        conn.close()

def get_latest_reading_for_device(device_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM readings
            WHERE device_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (device_id,)
        )
        return cursor.fetchone()
    finally:
        conn.close()

def get_readings_for_device(device_id: int, limit: int = 100) -> List[sqlite3.Row]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM readings
            WHERE device_id = ?
            ORDER BY received_at DESC
            LIMIT ?
            """,
            (device_id, limit)
        )
        return cursor.fetchall()
    finally:
        conn.close()

# ----------------- MANURE SAMPLES -----------------
def create_manure_sample(
    farmer_id: int,
    device_id: int,
    reading_id: Optional[int],
    temperature_c: float,
    moisture_percent: float,
    nitrogen: float,
    phosphorus: float,
    potassium: float,
    soil_type: str,
    preferred_crop: str
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            # Generate sequential sample code: SMP-0001, SMP-0002...
            cursor.execute("SELECT COUNT(*) AS cnt FROM manure_samples")
            count = cursor.fetchone()["cnt"] + 1
            sample_code = f"SMP-{count:04d}"

            cursor.execute(
                """
                INSERT INTO manure_samples (
                    sample_code, farmer_id, device_id, reading_id,
                    temperature_c, moisture_percent, nitrogen, phosphorus,
                    potassium, soil_type, preferred_crop, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    sample_code, farmer_id, device_id, reading_id,
                    round(float(temperature_c), 2), round(float(moisture_percent), 2),
                    round(float(nitrogen), 2), round(float(phosphorus), 2),
                    round(float(potassium), 2), soil_type.strip(), preferred_crop.strip()
                )
            )
            sample_id = cursor.lastrowid
            return {"id": sample_id, "sample_code": sample_code}
    finally:
        conn.close()

def get_samples_for_farmer(farmer_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.*, d.device_name
            FROM manure_samples s
            LEFT JOIN devices d ON s.device_id = d.id
            WHERE s.farmer_id = ?
            ORDER BY s.submitted_at DESC
            """,
            (farmer_id,)
        )
        return cursor.fetchall()
    finally:
        conn.close()

def get_all_samples_with_details() -> List[sqlite3.Row]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.*, u.name AS farmer_name, u.email AS farmer_email, d.device_name
            FROM manure_samples s
            JOIN users u ON s.farmer_id = u.id
            JOIN devices d ON s.device_id = d.id
            ORDER BY s.submitted_at DESC
            """
        )
        return cursor.fetchall()
    finally:
        conn.close()

def get_sample_by_id(sample_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.*, u.name AS farmer_name, u.email AS farmer_email, d.device_name
            FROM manure_samples s
            JOIN users u ON s.farmer_id = u.id
            JOIN devices d ON s.device_id = d.id
            WHERE s.id = ?
            """,
            (sample_id,)
        )
        return cursor.fetchone()
    finally:
        conn.close()

def update_sample_review(sample_id: int, status: str, reviewed_by: int, review_note: Optional[str]) -> bool:
    if status not in ("APPROVED", "REJECTED"):
        raise ValueError("Status must be either APPROVED or REJECTED")

    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            # Double approval prevention: only update if currently PENDING
            cursor.execute(
                """
                UPDATE manure_samples
                SET status = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP, review_note = ?
                WHERE id = ? AND status = 'PENDING'
                """,
                (status, reviewed_by, review_note.strip() if review_note else None, sample_id)
            )
            return cursor.rowcount > 0
    finally:
        conn.close()

# ----------------- PREDICTIONS -----------------
def create_prediction(sample_id: int, top1_crop: str, top2_crop: str, model_version: str) -> int:
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            # Prevent duplicate predictions per sample_id
            cursor.execute(
                """
                INSERT INTO predictions (sample_id, top1_crop, top2_crop, model_version)
                VALUES (?, ?, ?, ?)
                """,
                (sample_id, top1_crop, top2_crop, model_version)
            )
            return cursor.lastrowid
    finally:
        conn.close()

def get_prediction_for_sample(sample_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM predictions WHERE sample_id = ?", (sample_id,))
        return cursor.fetchone()
    finally:
        conn.close()

# ----------------- REPORTS -----------------
def save_report(sample_id: int, prediction_id: int, farmer_id: int, pdf_blob: bytes) -> int:
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO reports (sample_id, prediction_id, farmer_id, pdf_blob, delivery_status, created_at)
                VALUES (?, ?, ?, ?, 'NOT_SENT', CURRENT_TIMESTAMP)
                """,
                (sample_id, prediction_id, farmer_id, pdf_blob)
            )
            return cursor.lastrowid
    finally:
        conn.close()

def deliver_report(report_id: int) -> bool:
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE reports
                SET delivery_status = 'DELIVERED_IN_APP', delivered_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (report_id,)
            )
            return cursor.rowcount > 0
    finally:
        conn.close()

def get_report_for_sample(sample_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM reports
            WHERE sample_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (sample_id,)
        )
        return cursor.fetchone()
    finally:
        conn.close()

def get_delivered_crop_and_report_for_farmer(farmer_id: int) -> List[sqlite3.Row]:
    """Never show a prediction for unapproved or undelivered samples (enforced in the query)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.*, p.top1_crop, p.top2_crop, p.model_version,
                   r.id AS report_id, r.pdf_blob, r.delivery_status, r.delivered_at,
                   d.device_name
            FROM manure_samples s
            JOIN predictions p ON s.id = p.sample_id
            JOIN reports r ON s.id = r.sample_id
            LEFT JOIN devices d ON s.device_id = d.id
            WHERE s.farmer_id = ?
              AND s.status = 'APPROVED'
              AND r.delivery_status = 'DELIVERED_IN_APP'
            ORDER BY s.submitted_at DESC
            """,
            (farmer_id,)
        )
        return cursor.fetchall()
    finally:
        conn.close()

# ----------------- NOTIFICATIONS -----------------
def create_notification(farmer_id: int, report_id: Optional[int], message: str) -> int:
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO notifications (farmer_id, report_id, message, is_read)
                VALUES (?, ?, ?, 0)
                """,
                (farmer_id, report_id, message)
            )
            return cursor.lastrowid
    finally:
        conn.close()

def get_notifications_for_farmer(farmer_id: int, unread_only: bool = False) -> List[sqlite3.Row]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if unread_only:
            cursor.execute(
                """
                SELECT * FROM notifications
                WHERE farmer_id = ? AND is_read = 0
                ORDER BY created_at DESC
                """,
                (farmer_id,)
            )
        else:
            cursor.execute(
                """
                SELECT * FROM notifications
                WHERE farmer_id = ?
                ORDER BY created_at DESC
                """,
                (farmer_id,)
            )
        return cursor.fetchall()
    finally:
        conn.close()

def mark_notification_as_read(notif_id: int) -> bool:
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
            return cursor.rowcount > 0
    finally:
        conn.close()
