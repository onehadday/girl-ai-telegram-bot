import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

from server import analyze_screenshot, load_env_file, suggest
from storage import (
    add_conversation_message,
    clear_conversation_messages,
    list_conversation_messages,
    log_interaction,
)


API_BASE = "https://api.telegram.org/bot{token}/{method}"
FILE_BASE = "https://api.telegram.org/file/bot{token}/{path}"
MAX_TELEGRAM_MESSAGE = 3900
USER_SETTINGS = {}


def telegram_request(token, method, payload=None):
    url = API_BASE.format(token=token, method=method)
    if payload is None:
        with urllib.request.urlopen(url, timeout=35) as response:
            return json.loads(response.read().decode("utf-8"))

    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=35) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(token, chat_id, text):
    for chunk in split_message(text):
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
    return str(message.get("from", {}).get("id", "")) == allowed


def get_user_settings(message):
    user_id = str(message.get("from", {}).get("id", "default"))
    return USER_SETTINGS.setdefault(
        user_id,
        {
            "communicationMode": "Нормальний",
            "style": "коротко, природно, без пафосу, можна трохи жартувати",
            "phraseBank": "",
            "avoidPhrases": "",
            "activeChatKey": "",
            "activeChatName": "",
        },
    )


def stable_key(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:24]


def forwarded_conversation(message):
    origin = message.get("forward_origin") or {}
    origin_type = origin.get("type", "")
    if origin_type == "user":
        sender = origin.get("sender_user", {})
        name = " ".join(
            item for item in (sender.get("first_name", ""), sender.get("last_name", "")) if item
        ) or sender.get("username", "") or "Переслана переписка"
        return f"forward-user:{sender.get('id')}", name
    if origin_type == "hidden_user":
        name = origin.get("sender_user_name", "") or "Прихований користувач"
        return f"forward-hidden:{stable_key(name)}", name
    if origin_type == "chat":
        chat = origin.get("sender_chat", {})
        name = chat.get("title", "") or "Пересланий чат"
        return f"forward-chat:{chat.get('id')}", name

    sender = message.get("forward_from") or {}
    if sender:
        name = " ".join(
            item for item in (sender.get("first_name", ""), sender.get("last_name", "")) if item
        ) or sender.get("username", "") or "Переслана переписка"
        return f"forward-user:{sender.get('id')}", name
    return "", ""


def download_telegram_photo(token, message):
    photos = message.get("photo") or []
    if not photos:
        return None
    file_id = photos[-1].get("file_id")
    info = telegram_request(token, "getFile", {"file_id": file_id})
    file_path = info.get("result", {}).get("file_path", "")
    if not file_path:
        return None
    url = FILE_BASE.format(token=token, path=file_path)
    with urllib.request.urlopen(url, timeout=35) as response:
        raw = response.read(7 * 1024 * 1024 + 1)
    if len(raw) > 7 * 1024 * 1024:
        raise ValueError("Скріншот завеликий. Максимум 7 МБ.")
    mime_type = "image/png" if file_path.lower().endswith(".png") else "image/jpeg"
    return analyze_screenshot(base64.b64encode(raw).decode("ascii"), mime_type)["transcript"]


def make_payload(text, history, settings, person_name):
    transcript = "\n".join(f"{item['speaker']}: {item['content']}" for item in history)
    return {
        "situation": "Відповісти на останнє повідомлення",
        "tone": "спокійний, впевнений, живий",
        "language": "Українська",
        "goal": "природно продовжити спілкування",
        "style": settings.get("style", ""),
        "communicationMode": settings.get("communicationMode", "Нормальний"),
        "phraseBank": settings.get("phraseBank", ""),
        "avoidPhrases": settings.get("avoidPhrases", ""),
        "context": (
            f"Збережена переписка з {person_name or 'цією людиною'}:\n"
            f"{transcript or text}\n\n"
            "Запропонуй відповідь саме на останнє повідомлення."
        ),
        "variantSeed": int(time.time()) % 997,
    }


def help_text():
    return (
        "Надішли мені останнє повідомлення, перешли повідомлення з чату або кинь скріншот. "
        "Я прочитаю контекст і запропоную відповідь.\n\n"
        "Для окремої постійної переписки:\n"
        "/chat Аня — обрати або створити переписку\n"
        "/her текст — додати її повідомлення й отримати відповідь\n"
        "/me текст — записати твоє відправлене повідомлення\n"
        "/history — показати останні повідомлення\n"
        "/clear — очистити активну історію\n\n"
        "Також працюють /mode normal, /mode bydlo, /style, /phrases, /avoid, /settings та /id.\n\n"
        "Бот не надсилає повідомлення дівчині сам. Ти спочатку бачиш варіант і вирішуєш, чи копіювати його."
    )


def handle_message(token, message):
    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        return
    if not is_allowed(message):
        send_message(token, chat_id, "Цей бот приватний.")
        return

    text = (message.get("text") or message.get("caption") or "").strip()
    user = message.get("from", {})
    user_id = str(user.get("id", ""))
    owner_key = f"telegram:{user_id}"
    settings = get_user_settings(message)

    if text in ("/start", "/help"):
        send_message(token, chat_id, help_text())
        return
    if text == "/id":
        send_message(token, chat_id, f"Твій Telegram ID: {user_id}")
        return
    if text.startswith("/chat"):
        name = text.replace("/chat", "", 1).strip()
        if not name:
            send_message(token, chat_id, "Напиши ім'я після команди. Наприклад: /chat Аня")
            return
        settings["activeChatKey"] = f"named:{stable_key(name.lower())}"
        settings["activeChatName"] = name
        send_message(token, chat_id, f"Активна переписка: {name}. Тепер надсилай її повідомлення або скріншоти.")
        return
    if text.startswith("/mode"):
        value = text.replace("/mode", "", 1).strip().lower()
        if value in ("bydlo", "бидло", "грубо", "rough"):
            settings["communicationMode"] = "Режим бидла: грубувато, з матюками, але без принижень і тиску"
            send_message(token, chat_id, "Увімкнув грубуватий режим без принижень і тиску.")
        else:
            settings["communicationMode"] = "Нормальний"
            send_message(token, chat_id, "Увімкнув нормальний режим.")
        return
    if text.startswith("/style"):
        settings["style"] = text.replace("/style", "", 1).strip() or settings["style"]
        send_message(token, chat_id, "Стиль оновлено.")
        return
    if text.startswith("/phrases"):
        settings["phraseBank"] = text.replace("/phrases", "", 1).strip()
        send_message(token, chat_id, "Твої фрази збережено для цього запуску.")
        return
    if text.startswith("/avoid"):
        settings["avoidPhrases"] = text.replace("/avoid", "", 1).strip()
        send_message(token, chat_id, "Фрази-табу оновлено.")
        return
    if text == "/settings":
        send_message(
            token,
            chat_id,
            f"Режим: {settings['communicationMode']}\n"
            f"Стиль: {settings['style']}\n"
            f"Активна переписка: {settings['activeChatName'] or 'не обрана'}",
        )
        return

    forwarded_key, forwarded_name = forwarded_conversation(message)
    conversation_key = forwarded_key or settings.get("activeChatKey", "")
    person_name = forwarded_name or settings.get("activeChatName", "")
    if forwarded_key:
        settings["activeChatKey"] = forwarded_key
        settings["activeChatName"] = forwarded_name

    if text == "/history":
        if not conversation_key:
            send_message(token, chat_id, "Спочатку обери переписку командою /chat Ім'я.")
            return
        items = list_conversation_messages(owner_key, conversation_key, limit=15)
        transcript = "\n".join(f"{item['speaker']}: {item['content']}" for item in items)
        send_message(token, chat_id, transcript or "Історія поки порожня.")
        return
    if text == "/clear":
        if conversation_key:
            clear_conversation_messages(owner_key, conversation_key)
        send_message(token, chat_id, "Активну історію очищено.")
        return

    speaker = "Вона"
    should_suggest = True
    if text.startswith("/me "):
        speaker = "Я"
        text = text[4:].strip()
        should_suggest = False
    elif text.startswith("/her "):
        text = text[5:].strip()

    if message.get("photo"):
        send_message(token, chat_id, "Читаю скріншот...")
        try:
            text = download_telegram_photo(token, message) or ""
            speaker = "Переписка"
        except Exception as error:
            send_message(token, chat_id, f"Не вдалося прочитати скріншот: {error}")
            return

    if not text:
        send_message(token, chat_id, "Надішли текст, переслане повідомлення або скріншот переписки.")
        return

    if conversation_key:
        add_conversation_message(owner_key, conversation_key, person_name, speaker, text, "telegram")
        history = list_conversation_messages(owner_key, conversation_key, limit=40)
    else:
        history = [{"speaker": speaker, "content": text}]

    if not should_suggest:
        send_message(token, chat_id, "Записав твоє повідомлення в історію.")
        return

    send_message(token, chat_id, "Готую варіанти відповіді...")
    result = suggest(make_payload(text, history, settings, person_name))
    display_name = " ".join(
        item for item in (user.get("first_name", ""), user.get("last_name", "")) if item
    ) or user.get("username", "") or "Telegram"
    log_interaction(
        "telegram",
        text,
        result.get("text", ""),
        result.get("mode", ""),
        display_name=display_name,
        external_id=user_id,
    )
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
