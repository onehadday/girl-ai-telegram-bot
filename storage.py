import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone


DB_PATH = os.getenv("DB_PATH", "girl_ai.sqlite3")


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db():
    with db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                user_id INTEGER,
                display_name TEXT,
                external_id TEXT,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                mode TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"{salt}${digest.hex()}"


def verify_password(password, stored_hash):
    salt, expected = stored_hash.split("$", 1)
    actual = hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(actual, expected)


def first_user_will_be_admin(connection):
    row = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()
    return row["total"] == 0


def create_user(name, email, password):
    init_db()
    clean_email = email.strip().lower()
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    with db() as connection:
        is_admin = first_user_will_be_admin(connection) or (admin_email and clean_email == admin_email)
        cursor = connection.execute(
            """
            INSERT INTO users (name, email, password_hash, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name.strip() or "Користувач", clean_email, hash_password(password), int(is_admin), now_iso()),
        )
        return get_user_by_id(cursor.lastrowid, connection)


def authenticate_user(email, password):
    init_db()
    with db() as connection:
        user = connection.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            return None
        return row_to_user(user)


def create_session(user_id):
    init_db()
    token = secrets.token_urlsafe(32)
    with db() as connection:
        connection.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user_id, now_iso()),
        )
    return token


def delete_session(token):
    if not token:
        return
    init_db()
    with db() as connection:
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_user_by_session(token):
    if not token:
        return None
    init_db()
    with db() as connection:
        row = connection.execute(
            """
            SELECT users.* FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()
        return row_to_user(row) if row else None


def get_user_by_id(user_id, connection=None):
    own_connection = connection is None
    connection = connection or db()
    try:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return row_to_user(row) if row else None
    finally:
        if own_connection:
            connection.close()


def row_to_user(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "is_admin": bool(row["is_admin"]),
        "created_at": row["created_at"],
    }


def log_interaction(source, prompt, response, mode="", user=None, display_name="", external_id=""):
    init_db()
    with db() as connection:
        connection.execute(
            """
            INSERT INTO interactions (source, user_id, display_name, external_id, prompt, response, mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                user["id"] if user else None,
                display_name,
                external_id,
                prompt,
                response,
                mode,
                now_iso(),
            ),
        )


def list_interactions(limit=80):
    init_db()
    with db() as connection:
        rows = connection.execute(
            """
            SELECT interactions.*, users.email AS user_email
            FROM interactions
            LEFT JOIN users ON users.id = interactions.user_id
            ORDER BY interactions.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
