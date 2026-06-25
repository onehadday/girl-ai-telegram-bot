from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from storage import (
    authenticate_user,
    change_user_password,
    create_session,
    create_user,
    delete_session,
    get_user_by_session,
    init_db,
    list_people,
    list_interactions,
    log_interaction,
)


PORT = int(os.getenv("PORT", "8000"))
OPENAI_URL = "https://api.openai.com/v1/responses"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"


def load_env_file():
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.lstrip("\ufeff")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_prompt(data):
    language = data.get("language", "Українська")
    situation = data.get("situation", "Продовжити переписку")
    tone = data.get("tone", "спокійний, впевнений, живий")
    goal = data.get("goal", "підтримати нормальне спілкування")
    context = data.get("context", "").strip()
    user_style = data.get("style", "").strip()
    communication_mode = data.get("communicationMode", "Нормальний")
    phrase_bank = data.get("phraseBank", "").strip()
    avoid_phrases = data.get("avoidPhrases", "").strip()
    is_rough = "бидл" in communication_mode.lower() or "груб" in communication_mode.lower()
    rough_rules = ""
    if is_rough:
        rough_rules = """
Окремі правила для режиму "бидла":
- Стиль має бути дворовий, прямий, трохи наглий, з легкою лайкою.
- Можна використовувати слова типу: блін, капець, нафіг, охріненно, та ну, погнали.
- Не перетворюй це на офіційний або надто чемний стиль.
- Не ображай дівчину, не називай її принизливо, не тисни на неї.
- Найкращий варіант і хоча б один додатковий варіант мають звучати реально грубіше, а не просто "впевнено".
""".strip()

    return f"""
Ти персональний помічник для переписки у знайомствах.
Завдання: допомогти чоловіку написати природну, поважну, не нав'язливу відповідь.

Правила:
- Не маніпулюй, не тисни, не вигадуй факти про користувача.
- Не радь писати багато повідомлень підряд, якщо це виглядає нав'язливо.
- Якщо краще не писати зараз, скажи це прямо і дай м'яку альтернативу.
- Пиши живо, без канцеляриту і без шаблонного пікапу.
- Відповіді мають звучати як реальна людина, а не як робот.
- Якщо в переписці є явний холод або відмова, поважай це.
- Якщо обрано грубий режим, можна писати простіше, різкіше і з легкою лайкою, але не ображай дівчину, не принижуй її і не тисни.
- Використовуй фрази користувача тільки там, де вони звучать природно.
- Не використовуй фрази-табу.
- Не використовуй Markdown: ніяких ###, **, *, списків із зірочками або декоративних розділювачів.
- Не став повідомлення в кутові лапки «...». Просто пиши текст повідомлення.

Мова відповіді: {language}
Ситуація: {situation}
Бажаний тон: {tone}
Ціль: {goal}
Режим спілкування: {communication_mode}
Стиль користувача: {user_style or "простий, природний, без пафосу"}
Фрази користувача, які можна вплітати: {phrase_bank or "немає"}
Фрази-табу, яких треба уникати: {avoid_phrases or "немає"}
{rough_rules}

Переписка або опис ситуації:
{context}

Поверни відповідь у такому форматі:
AI-аналіз:
Зацікавленість: число від 0 до 100
Флірт: низький / середній / високий
Настрій: нейтральний / теплий / фліртовий / провокативний / холодний
Рекомендація: відповідати спокійно / з гумором / сміливіше / не поспішати
Коли відповідати: зараз / через 5-10 хвилин / через 20-30 хвилин / краще не відповідати одразу

Найкращий варіант:
текст повідомлення

Ще варіанти:
М'якше: текст
Сміливіше: текст
З гумором: текст

Чому це працює:
коротке пояснення

Що не варто писати:
коротке попередження
""".strip()


def fallback_reply(data):
    situation = data.get("situation", "")
    language = data.get("language", "Українська")
    communication_mode = data.get("communicationMode", "Нормальний")
    phrase_bank = data.get("phraseBank", "").strip()
    is_ua = "english" not in language.lower()
    is_rough = "бидл" in communication_mode.lower() or "груб" in communication_mode.lower()

    if is_ua:
        opener = "Мені здається, тут краще написати легко і без тиску."
        if "глухий" in situation.lower() or "мовч" in situation.lower():
            best = "Слухай, я щось згадав нашу розмову і подумав: а який у тебе зараз найприємніший план на тиждень?"
        elif "запрос" in situation.lower() or "зустр" in situation.lower():
            best = "Мені з тобою цікаво спілкуватись. Може, вип'ємо кави цього тижня і продовжимо вже наживо?"
        else:
            best = "Ахах, звучить цікаво. А як ти взагалі до цього прийшла?"
        if is_rough:
            opener = "Ок, даю грубіший варіант, але без наїзду."
            if "глухий" in situation.lower() or "мовч" in situation.lower():
                best = "Та блін, згадав нашу розмову. Як у тебе там життя, який план на тиждень?"
            elif "запрос" in situation.lower() or "зустр" in situation.lower():
                best = "Слухай, досить оце тільки переписуватись. Погнали на каву цього тижня?"
            else:
                best = "Ахах, ну це вже цікаво. Давай повну версію, бо я тепер не відчеплюсь."
        if phrase_bank:
            best = f"{best}\n\nМожна з твоєю фразою: {phrase_bank.splitlines()[0][:120]}"
        return f"""{opener}

AI-аналіз:
Зацікавленість: 48
Флірт: низький
Настрій: нейтральний
Рекомендація: відповідати спокійно
Коли відповідати: через 5-10 хвилин

1. Найкращий варіант:
{best}

2. Ще варіанти:
М'якше: "До речі, як у тебе день проходить?"
Сміливіше: "Ти цікава. Хочу краще тебе зрозуміти, розкажеш трохи більше?"
З гумором: "Окей, тепер мені потрібна повна версія цієї історії, бо тизер вийшов сильний."

3. Чому це працює:
Повідомлення коротке, не просить уваги силою і дає їй легку тему для відповіді.

4. Що не варто писати:
Не пиши докори типу "чого мовчиш", не засипай повідомленнями і не роби вигляд, що тобі байдуже, якщо це не так.

Примітка: це локальна підказка. Якщо API-ключ уже додано, але ти бачиш цей режим, безкоштовний API тимчасово недоступний або вперся в ліміт."""

    return """1. Best message:
Hey, this made me curious. How did you even get into that?

2. Other options:
Softer: "By the way, how is your day going?"
Bolder: "You're interesting. I want to understand you better."
Funny: "Okay, now I need the full story, because the teaser is too good."

3. Why it works:
It is short, calm, and gives her an easy way to continue.

4. Avoid:
Do not guilt-trip her for silence or send several messages in a row.

Note: this is a local fallback. If an API key is already configured, the free API is temporarily unavailable or rate-limited."""


def call_openai(data):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    prompt = build_prompt(data)
    payload = {
        "model": model,
        "input": prompt,
        "temperature": 0.8,
        "max_output_tokens": 1200,
    }
    result = post_json(
        OPENAI_URL,
        payload,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    text = result.get("output_text", "").strip()
    if not text:
        chunks = []
        for item in result.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in ("output_text", "text"):
                    chunks.append(content.get("text", ""))
        text = "\n".join(chunks).strip()

    return {"text": text or "Не вдалося прочитати відповідь моделі.", "mode": "OpenAI"}


def call_openrouter(data):
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    model = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": build_prompt(data)}],
        "temperature": 0.8,
        "max_tokens": 1200,
    }
    result = post_json(
        OPENROUTER_URL,
        payload,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:8000",
            "X-Title": "Dating Assistant",
        },
    )
    text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    return {"text": text or "Не вдалося прочитати відповідь OpenRouter.", "mode": "OpenRouter"}


def call_gemini(data, model=None):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
    generation_config = {
        "temperature": 0.8,
        "maxOutputTokens": 2048,
    }
    if model.startswith("gemini-2.5") or model.startswith("gemini-3"):
        generation_config["thinkingConfig"] = {"thinkingBudget": 0}

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": build_prompt(data),
                    }
                ]
            }
        ],
        "generationConfig": generation_config,
    }
    url = GEMINI_URL_TEMPLATE.format(model=model, api_key=api_key)
    result = post_json(url, payload, {"Content-Type": "application/json"})
    chunks = []
    for candidate in result.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            chunks.append(part.get("text", ""))
    text = "\n".join(chunks).strip()
    return {"text": text or "Не вдалося прочитати відповідь Gemini.", "mode": f"Gemini: {model}"}


def post_json(url, payload, headers):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API error {error.code}: {details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Network error: {error.reason}") from error


def suggest(data):
    if os.getenv("GEMINI_API_KEY", "").strip():
        models = [
            os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite").strip(),
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
            "gemini-flash-lite-latest",
            "gemini-2.5-flash-lite",
        ]
        seen = set()
        errors = []
        for model in models:
            if not model or model in seen:
                continue
            seen.add(model)
            try:
                return call_gemini(data, model)
            except Exception as error:
                errors.append(f"{model}: {error}")
                continue
        error_text = summarize_api_errors(errors)
        return {
            "text": f"Gemini зараз не відповів нормально на безкоштовних моделях, тому даю локальну підказку.\n\n{error_text}\n\n{fallback_reply(data)}",
            "mode": "Gemini недоступний",
        }
    if os.getenv("OPENROUTER_API_KEY", "").strip():
        try:
            return call_openrouter(data)
        except Exception as error:
            return {
                "text": f"OpenRouter зараз не відповів нормально, тому даю локальну підказку.\n\n{short_error(error)}\n\n{fallback_reply(data)}",
                "mode": "OpenRouter недоступний",
            }
    if os.getenv("OPENAI_API_KEY", "").strip():
        try:
            return call_openai(data)
        except Exception as error:
            return {
                "text": f"OpenAI зараз не відповів нормально, тому даю локальну підказку.\n\n{short_error(error)}\n\n{fallback_reply(data)}",
                "mode": "OpenAI недоступний",
            }
    return {"text": fallback_reply(data), "mode": "Локальний режим"}


def short_error(error):
    message = str(error)
    if "429" in message or "RESOURCE_EXHAUSTED" in message or "quota" in message.lower():
        return "Причина: безкоштовний ліміт API зараз вичерпано або недоступний."
    if "503" in message or "UNAVAILABLE" in message or "high demand" in message.lower():
        return "Причина: модель тимчасово перевантажена."
    if "timed out" in message.lower() or "timeout" in message.lower():
        return "Причина: API відповідав занадто довго."
    return "Причина: тимчасова помилка API."


def summarize_api_errors(errors):
    joined = "\n".join(errors)
    parts = []
    if "429" in joined or "RESOURCE_EXHAUSTED" in joined or "quota" in joined.lower():
        parts.append("Частина моделей зараз має нульовий або вичерпаний free-tier ліміт.")
    if "503" in joined or "UNAVAILABLE" in joined or "high demand" in joined.lower():
        parts.append("Частина моделей тимчасово перевантажена.")
    if not parts:
        parts.append("Є тимчасова помилка API.")
    return " ".join(parts)


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/me":
            self.handle_me()
            return
        if path == "/api/admin/history":
            self.handle_history()
            return
        if path == "/api/admin/users":
            self.handle_users()
            return
        super().do_GET()

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
        if self.path == "/api/change-password":
            self.handle_change_password()
            return
        if self.path == "/api/admin/reset-password":
            self.handle_reset_password()
            return
        if self.path != "/api/suggest":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            user = self.current_user()
            if not user:
                self.send_json(401, {"error": "Спочатку зареєструйся або увійди в акаунт."})
                return
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            result = suggest(data)
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
        self.send_session_json(200, "", {"ok": True})

    def handle_change_password(self):
        user = self.current_user()
        if not user:
            self.send_json(401, {"error": "Спочатку увійди."})
            return
        data = self.read_json()
        new_password = data.get("new_password", "")
        if len(new_password) < 6:
            self.send_json(400, {"error": "Новий пароль має бути хоча б 6 символів."})
            return
        change_user_password(user["id"], new_password)
        self.send_json(200, {"ok": True})

    def handle_me(self):
        self.send_json(200, {"user": self.current_user()})

    def handle_users(self):
        user = self.current_user()
        if not user or not user.get("is_admin"):
            self.send_json(403, {"error": "Доступ тільки для адміна."})
            return
        self.send_json(200, {"users": list_people()})

    def handle_history(self):
        user = self.current_user()
        if not user or not user.get("is_admin"):
            self.send_json(403, {"error": "Доступ тільки для адміна."})
            return
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        user_id = query.get("user_id", [""])[0]
        source = query.get("source", [""])[0]
        external_id = query.get("external_id", [""])[0]
        self.send_json(
            200,
            {
                "items": list_interactions(
                    user_id=int(user_id) if user_id else None,
                    source=source or None,
                    external_id=external_id or None,
                )
            },
        )

    def handle_reset_password(self):
        admin = self.current_user()
        if not admin or not admin.get("is_admin"):
            self.send_json(403, {"error": "Доступ тільки для адміна."})
            return
        data = self.read_json()
        user_id = data.get("user_id")
        new_password = data.get("new_password", "")
        if not user_id:
            self.send_json(400, {"error": "Обери користувача сайту."})
            return
        if len(new_password) < 6:
            self.send_json(400, {"error": "Новий пароль має бути хоча б 6 символів."})
            return
        change_user_password(int(user_id), new_password)
        self.send_json(200, {"ok": True})

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


if __name__ == "__main__":
    load_env_file()
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Dating assistant is running: http://127.0.0.1:{PORT}")
    server.serve_forever()
