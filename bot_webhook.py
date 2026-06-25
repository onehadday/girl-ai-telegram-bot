from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
import urllib.error

from server import load_env_file, suggest
from storage import (
    authenticate_user,
    create_session,
    create_user,
    delete_session,
    get_user_by_session,
    init_db,
    list_interactions,
    log_interaction,
)
from telegram_bot import handle_message, telegram_request


def env(name, default=""):
    return os.getenv(name, default).strip()


def set_webhook_if_configured():
    token = env("TELEGRAM_BOT_TOKEN")
    public_url = env("PUBLIC_URL")
    secret = env("TELEGRAM_WEBHOOK_SECRET")

    if not token or not public_url or not secret:
        return

    webhook_url = f"{public_url.rstrip('/')}/telegram/{secret}"
    payload = {
        "url": webhook_url,
        "allowed_updates": ["message", "edited_message"],
    }
    telegram_request(token, "setWebhook", payload)
    print("Telegram webhook configured.")


class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_text(200, "Bot is alive.")
            return
        if self.path == "/api/me":
            self.handle_me()
            return
        if self.path == "/api/admin/history":
            self.handle_history()
            return
        if self.path == "/" or self.path in ("/chat", "/settings", "/profile"):
            self.send_static("index.html")
            return
        if self.path in ("/app.js", "/styles.css"):
            self.send_static(self.path.lstrip("/"))
            return
        self.send_text(404, "Not found.")

    def do_POST(self):
        if self.path == "/api/register":
            self.handle_register()
            return
        if self.path == "/api/login":
            self.handle_login()
            return
        if self.path == "/api/logout":
            self.handle_logout()
            return
        if self.path == "/api/suggest":
            self.handle_suggest()
            return

        secret = env("TELEGRAM_WEBHOOK_SECRET")
        expected_path = f"/telegram/{secret}"
        if not secret or self.path != expected_path:
            self.send_text(404, "Not found.")
            return

        token = env("TELEGRAM_BOT_TOKEN")
        length = int(self.headers.get("Content-Length", "0"))

        try:
            update = json.loads(self.rfile.read(length).decode("utf-8"))
            message = update.get("message") or update.get("edited_message")
            if message:
                handle_message(token, message)
            self.send_json(200, {"ok": True})
        except Exception as error:
            print(f"Webhook error: {error}")
            self.send_json(200, {"ok": False})

    def handle_suggest(self):
        length = int(self.headers.get("Content-Length", "0"))
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            result = suggest(data)
            user = self.current_user()
            log_interaction(
                "site",
                data.get("context", ""),
                result.get("text", ""),
                result.get("mode", ""),
                user=user,
                display_name=user["name"] if user else "Гість",
            )
            self.send_json(200, result)
        except Exception as error:
            self.send_json(500, {"error": str(error)})

    def handle_register(self):
        data = self.read_json()
        name = data.get("name", "").strip()
        email = data.get("email", "").strip()
        password = data.get("password", "")
        if not email or not password:
            self.send_json(400, {"error": "Email і пароль обов'язкові."})
            return
        if len(password) < 6:
            self.send_json(400, {"error": "Пароль має бути хоча б 6 символів."})
            return
        try:
            user = create_user(name, email, password)
        except Exception:
            self.send_json(400, {"error": "Такий email уже зареєстрований."})
            return
        token = create_session(user["id"])
        self.send_session_json(200, token, {"user": user})

    def handle_login(self):
        data = self.read_json()
        user = authenticate_user(data.get("email", ""), data.get("password", ""))
        if not user:
            self.send_json(401, {"error": "Неправильний email або пароль."})
            return
        token = create_session(user["id"])
        self.send_session_json(200, token, {"user": user})

    def handle_logout(self):
        delete_session(self.session_token())
        self.send_session_json(200, "", {"ok": True, "clear": True})

    def handle_me(self):
        self.send_json(200, {"user": self.current_user()})

    def handle_history(self):
        user = self.current_user()
        if not user or not user.get("is_admin"):
            self.send_json(403, {"error": "Доступ тільки для адміна."})
            return
        self.send_json(200, {"items": list_interactions()})

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def session_token(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            key, _, value = part.strip().partition("=")
            if key == "girl_ai_session":
                return value
        return ""

    def current_user(self):
        return get_user_by_session(self.session_token())

    def log_message(self, format, *args):
        return

    def send_text(self, status, text):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, path):
        if not os.path.exists(path):
            self.send_text(404, "Not found.")
            return

        with open(path, "rb") as file:
            body = file.read()
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if path.endswith(".html"):
            content_type = "text/html; charset=utf-8"
        elif path.endswith(".js"):
            content_type = "text/javascript; charset=utf-8"
        elif path.endswith(".css"):
            content_type = "text/css; charset=utf-8"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_session_json(self, status, token, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if token:
            self.send_header("Set-Cookie", f"girl_ai_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000")
        else:
            self.send_header("Set-Cookie", "girl_ai_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_webhook_server():
    load_env_file()
    init_db()
    if not env("TELEGRAM_BOT_TOKEN"):
        raise SystemExit("Add TELEGRAM_BOT_TOKEN to environment variables.")
    if not env("TELEGRAM_ALLOWED_USER_ID"):
        print("Warning: TELEGRAM_ALLOWED_USER_ID is empty, bot is not private.")
    if not env("TELEGRAM_WEBHOOK_SECRET"):
        raise SystemExit("Add TELEGRAM_WEBHOOK_SECRET to environment variables.")

    try:
        set_webhook_if_configured()
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        print(f"Could not configure webhook: {details}")
    except Exception as error:
        print(f"Could not configure webhook: {error}")

    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), WebhookHandler)
    print(f"Webhook bot is running on port {port}.")
    server.serve_forever()


if __name__ == "__main__":
    run_webhook_server()
