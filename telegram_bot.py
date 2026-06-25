import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from server import load_env_file, suggest


API_BASE = "https://api.telegram.org/bot{token}/{method}"
MAX_TELEGRAM_MESSAGE = 3900


def telegram_request(token, method, payload=None):
    url = API_BASE.format(token=token, method=method)
    if payload is None:
        with urllib.request.urlopen(url, timeout=35) as response:
            return json.loads(response.read().decode("utf-8"))

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=35) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(token, chat_id, text):
    chunks = split_message(text)
    for chunk in chunks:
        telegram_request(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            },
        )


def split_message(text):
    if len(text) <= MAX_TELEGRAM_MESSAGE:
        return [text]

    chunks = []
    current = text
    while len(current) > MAX_TELEGRAM_MESSAGE:
        split_at = current.rfind("\n", 0, MAX_TELEGRAM_MESSAGE)
        if split_at < 1000:
            split_at = MAX_TELEGRAM_MESSAGE
        chunks.append(current[:split_at].strip())
        current = current[split_at:].strip()
    if current:
        chunks.append(current)
    return chunks


def is_allowed(message):
    allowed = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
    if not allowed:
        return True

    user = message.get("from", {})
    return str(user.get("id", "")) == allowed


def make_payload(text):
    lowered = text.lower()
    situation = "Відповісти на її повідомлення"
    goal = "підтримати нормальне спілкування"

    if "мовч" in lowered or "не відповіда" in lowered or "глухий" in lowered:
        situation = "Переписка зайшла в глухий кут"
        goal = "м'яко відновити розмову"
    elif "зустр" in lowered or "кава" in lowered or "побач" in lowered:
        situation = "Запросити на зустріч"
        goal = "запросити без тиску"
    elif "почати" in lowered or "перш" in lowered:
        situation = "Почати спілкування після знайомства"
        goal = "почати розмову природно"

    return {
        "situation": situation,
        "tone": "спокійний, впевнений, живий",
        "language": "Українська",
        "goal": goal,
        "style": "коротко, без пафосу, можна трохи жартувати",
        "context": text,
    }


def handle_message(token, message):
    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or message.get("caption") or "").strip()

    if not chat_id:
        return

    if not is_allowed(message):
        send_message(token, chat_id, "Цей бот приватний.")
        return

    if text in ("/start", "/help"):
        send_message(
            token,
            chat_id,
            "Привіт. Кидай сюди переписку або коротко опиши ситуацію, а я дам варіанти що відповісти.\n\n"
            "Приклад:\n"
            "Вона 2 дні не відповідає. До цього писала, що любить каву. Хочу написати без нав'язливості.\n\n"
            "Команда /id покаже твій Telegram ID, щоб за бажанням закрити бота тільки для тебе.",
        )
        return

    if text == "/id":
        user_id = message.get("from", {}).get("id", "невідомо")
        send_message(token, chat_id, f"Твій Telegram ID: {user_id}")
        return

    if not text:
        send_message(token, chat_id, "Надішли текст переписки або короткий опис ситуації.")
        return

    send_message(token, chat_id, "Думаю, що можна відповісти...")
    result = suggest(make_payload(text))
    send_message(token, chat_id, result.get("text", "Не вдалося підготувати відповідь."))


def run_bot():
    load_env_file()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Додай TELEGRAM_BOT_TOKEN у файл .env")

    offset = None
    print("Telegram bot is running. Press Ctrl+C to stop.")

    while True:
        try:
            payload = {"timeout": 30}
            if offset is not None:
                payload["offset"] = offset

            updates = telegram_request(token, "getUpdates", payload)
            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message") or update.get("edited_message")
                if message:
                    handle_message(token, message)
        except KeyboardInterrupt:
            print("Telegram bot stopped.")
            break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
            print(f"Temporary Telegram error: {error}")
            time.sleep(5)
        except Exception as error:
            print(f"Bot error: {error}")
            time.sleep(5)


if __name__ == "__main__":
    run_bot()
