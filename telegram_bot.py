import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from server import load_env_file, suggest


API_BASE = "https://api.telegram.org/bot{token}/{method}"
MAX_TELEGRAM_MESSAGE = 3900
USER_SETTINGS = {}


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

    settings = USER_SETTINGS.get("default", {})
    return {
        "situation": situation,
        "tone": "спокійний, впевнений, живий",
        "language": "Українська",
        "goal": goal,
        "style": settings.get("style", "коротко, без пафосу, можна трохи жартувати"),
        "communicationMode": settings.get("communicationMode", "Нормальний"),
        "phraseBank": settings.get("phraseBank", ""),
        "avoidPhrases": settings.get("avoidPhrases", ""),
        "context": text,
    }


def get_user_settings(message):
    user_id = str(message.get("from", {}).get("id", "default"))
    return USER_SETTINGS.setdefault(
        user_id,
        {
            "communicationMode": "Нормальний",
            "style": "коротко, без пафосу, можна трохи жартувати",
            "phraseBank": "",
            "avoidPhrases": "",
        },
    )


def make_payload_for_user(text, message):
    payload = make_payload(text)
    settings = get_user_settings(message)
    payload.update(settings)
    return payload


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
            "Команди:\n"
            "/mode normal - нормальний режим\n"
            "/mode bydlo - грубіше, з матюками, але без принижень\n"
            "/style коротко, без пафосу - задати стиль\n"
            "/phrases твоя фраза; ще фраза - додати твої фрази\n"
            "/avoid фраза; інша фраза - що не використовувати\n"
            "/settings - показати налаштування\n"
            "/id - показати твій Telegram ID",
        )
        return

    if text == "/id":
        user_id = message.get("from", {}).get("id", "невідомо")
        send_message(token, chat_id, f"Твій Telegram ID: {user_id}")
        return

    if text.startswith("/mode"):
        settings = get_user_settings(message)
        value = text.replace("/mode", "", 1).strip().lower()
        if value in ("bydlo", "бидло", "грубо"):
            settings["communicationMode"] = "Режим бидла: грубо, з матюками, але без принижень"
            send_message(token, chat_id, "Увімкнув грубіший режим. Матюки можна, принижувати її - ні.")
        else:
            settings["communicationMode"] = "Нормальний"
            send_message(token, chat_id, "Увімкнув нормальний режим.")
        return

    if text.startswith("/phrases"):
        settings = get_user_settings(message)
        settings["phraseBank"] = text.replace("/phrases", "", 1).strip()
        send_message(token, chat_id, "Зберіг твої фрази для цього запуску бота.")
        return

    if text.startswith("/style"):
        settings = get_user_settings(message)
        settings["style"] = text.replace("/style", "", 1).strip() or "коротко, без пафосу"
        send_message(token, chat_id, "Ок, стиль оновив.")
        return

    if text.startswith("/avoid"):
        settings = get_user_settings(message)
        settings["avoidPhrases"] = text.replace("/avoid", "", 1).strip()
        send_message(token, chat_id, "Ок, ці фрази буду обходити.")
        return

    if text == "/settings":
        settings = get_user_settings(message)
        send_message(
            token,
            chat_id,
            "Поточні налаштування:\n"
            f"Режим: {settings.get('communicationMode')}\n"
            f"Стиль: {settings.get('style')}\n"
            f"Твої фрази: {settings.get('phraseBank') or 'немає'}\n"
            f"Не писати: {settings.get('avoidPhrases') or 'немає'}",
        )
        return

    if not text:
        send_message(token, chat_id, "Надішли текст переписки або короткий опис ситуації.")
        return

    send_message(token, chat_id, "Думаю, що можна відповісти...")
    result = suggest(make_payload_for_user(text, message))
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
