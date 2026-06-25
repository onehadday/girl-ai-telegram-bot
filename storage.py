import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse


DB_PATH = os.getenv("DB_PATH", "girl_ai.sqlite3")


def database_url():
    return os.getenv("DATABASE_URL", "").strip()


def using_postgres():
    return bool(database_url())


def normalize_database_url(url):
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


@contextmanager
def db():
    if using_postgres():
        import psycopg
        from psycopg.rows import dict_row

        connection = psycopg.connect(normalize_database_url(database_url()), row_factory=dict_row)
    else:
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def placeholder(index):
    return "%s" if using_postgres() else "?"


def limit_clause():
    return "LIMIT %s" if using_postgres() else "LIMIT ?"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db():
    with db() as connection:
        if using_postgres():
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
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
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    id SERIAL PRIMARY KEY,
                    source TEXT NOT NULL,
                    user_id INTEGER REFERENCES users(id),
                    display_name TEXT,
                    external_id TEXT,
                    prompt TEXT NOT NULL,
                    response TEXT NOT NULL,
                    mode TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
        else:
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

        admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
        if admin_email:
            connection.execute(
                f"UPDATE users SET is_admin = 1 WHERE email = {placeholder(1)}",
                (admin_email,),
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
        if using_postgres():
            row = connection.execute(
                """
                INSERT INTO users (name, email, password_hash, is_admin, created_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (name.strip() or "Користувач", clean_email, hash_password(password), int(is_admin), now_iso()),
            ).fetchone()
            user_id = row["id"]
        else:
            cursor = connection.execute(
                """
                INSERT INTO users (name, email, password_hash, is_admin, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name.strip() or "Користувач", clean_email, hash_password(password), int(is_admin), now_iso()),
            )
            user_id = cursor.lastrowid
        return get_user_by_id(user_id, connection)


def authenticate_user(email, password):
    init_db()
    with db() as connection:
        user = connection.execute(
            f"SELECT * FROM users WHERE email = {placeholder(1)}",
            (email.strip().lower(),),
        ).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            return None
        return row_to_user(user)


def create_session(user_id):
    init_db()
    token = secrets.token_urlsafe(32)
    with db() as connection:
        connection.execute(
            f"INSERT INTO sessions (token, user_id, created_at) VALUES ({placeholder(1)}, {placeholder(2)}, {placeholder(3)})",
            (token, user_id, now_iso()),
        )
    return token


def delete_session(token):
    if not token:
        return
    init_db()
    with db() as connection:
        connection.execute(f"DELETE FROM sessions WHERE token = {placeholder(1)}", (token,))


def get_user_by_session(token):
    if not token:
        return None
    init_db()
    with db() as connection:
        row = connection.execute(
            f"""
            SELECT users.* FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = {placeholder(1)}
            """,
            (token,),
        ).fetchone()
        return row_to_user(row) if row else None


def get_user_by_id(user_id, connection=None):
    if connection is not None:
        row = connection.execute(f"SELECT * FROM users WHERE id = {placeholder(1)}", (user_id,)).fetchone()
        return row_to_user(row) if row else None
    with db() as connection:
        row = connection.execute(f"SELECT * FROM users WHERE id = {placeholder(1)}", (user_id,)).fetchone()
        return row_to_user(row) if row else None


def change_user_password(user_id, new_password):
    init_db()
    with db() as connection:
        connection.execute(
            f"UPDATE users SET password_hash = {placeholder(1)} WHERE id = {placeholder(2)}",
            (hash_password(new_password), user_id),
        )


def list_people():
    init_db()
    with db() as connection:
        registered = connection.execute(
            """
            SELECT users.id, users.name, users.email, users.is_admin, users.created_at,
                   COUNT(interactions.id) AS messages_count,
                   MAX(interactions.created_at) AS last_seen
            FROM users
            LEFT JOIN interactions ON interactions.user_id = users.id
            GROUP BY users.id, users.name, users.email, users.is_admin, users.created_at
            ORDER BY last_seen DESC, users.created_at DESC
            """
        ).fetchall()
        telegram = connection.execute(
            """
            SELECT external_id, display_name, COUNT(*) AS messages_count,
                   MAX(created_at) AS last_seen
            FROM interactions
            WHERE source = 'telegram' AND user_id IS NULL AND external_id != ''
            GROUP BY external_id, display_name
            ORDER BY last_seen DESC
            """
        ).fetchall()

    people = [
        {
            "kind": "site",
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "is_admin": bool(row["is_admin"]),
            "created_at": row["created_at"],
            "messages_count": row["messages_count"],
            "last_seen": row["last_seen"],
        }
        for row in registered
    ]
    people.extend(
        {
            "kind": "telegram",
            "id": row["external_id"],
            "name": row["display_name"] or "Telegram",
            "email": "",
            "is_admin": False,
            "created_at": "",
            "messages_count": row["messages_count"],
            "last_seen": row["last_seen"],
        }
        for row in telegram
    )
    return people


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
            f"""
            INSERT INTO interactions (source, user_id, display_name, external_id, prompt, response, mode, created_at)
            VALUES ({placeholder(1)}, {placeholder(2)}, {placeholder(3)}, {placeholder(4)}, {placeholder(5)}, {placeholder(6)}, {placeholder(7)}, {placeholder(8)})
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


def list_interactions(limit=80, user_id=None, source=None, external_id=None):
    init_db()
    with db() as connection:
        where = []
        params = []
        if user_id:
            where.append(f"interactions.user_id = {placeholder(len(params) + 1)}")
            params.append(user_id)
        if source:
            where.append(f"interactions.source = {placeholder(len(params) + 1)}")
            params.append(source)
        if external_id:
            where.append(f"interactions.external_id = {placeholder(len(params) + 1)}")
            params.append(external_id)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        rows = connection.execute(
            f"""
            SELECT interactions.*, users.email AS user_email
            FROM interactions
            LEFT JOIN users ON users.id = interactions.user_id
            {where_sql}
            ORDER BY interactions.id DESC
            {limit_clause()}
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
