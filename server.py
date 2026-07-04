from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from storage import (
    add_conversation_message,
    authenticate_user,
    change_user_password,
    clear_conversation_messages,
    create_session,
    create_user,
    delete_session,
    get_user_by_session,
    init_db,
    list_conversations,
    list_conversation_messages,
    list_people,
    list_interactions,
    log_interaction,
)


PORT = int(os.getenv("PORT", "8000"))
OPENAI_URL = "https://api.openai.com/v1/responses"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"


def gemini_model_candidates():
    configured = os.getenv("GEMINI_MODEL", "").strip()
    models = [
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-flash-latest",
        "gemini-2.5-flash-lite",
    ]
    if configured and not configured.startswith("gemini-2.0"):
        models.insert(1, configured)
    return list(dict.fromkeys(models))


def text_blob(data):
    return " ".join(
        str(data.get(key, ""))
        for key in ("context", "situation", "goal", "tone", "style")
    ).lower()


def is_intimate_context(data):
    blob = text_blob(data)
    intimate_words = (
        "секс",
        "інтим",
        "пересп",
        "зайнят",
        "згадати старе",
        "згадати минуле",
        "ніч разом",
        "хочу тебе",
        "близьк",
        "пристрас",
        "поціл",
        "обійм",
        "ліжк",
    )
    return any(word in blob for word in intimate_words)


def variant_index(data, total):
    if total <= 1:
        return 0
    try:
        return int(data.get("variantSeed", 0) or 0) % total
    except (TypeError, ValueError):
        return 0


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
    intimate_rules = ""
    if is_rough:
        rough_rules = """
Окремі правила для режиму "бидла":
- Стиль має бути дворовий, прямий, трохи наглий, з легкою лайкою.
- Можна використовувати слова типу: блін, капець, нафіг, охріненно, та ну, погнали.
- Не перетворюй це на офіційний або надто чемний стиль.
- Не ображай дівчину, не називай її принизливо, не тисни на неї.
- Найкращий варіант і хоча б один додатковий варіант мають звучати реально грубіше, а не просто "впевнено".
""".strip()
    if is_intimate_context(data):
        intimate_rules = """
Окремі правила для дорослого інтимного контексту:
- Якщо з опису видно взаємну дорослу інтимну пропозицію, не тікай від теми в "як день?" або загальні питання.
- Відповідай прямо на її пропозицію: тепло, впевнено, фліртово і без сорому.
- Не пиши графічних сексуальних деталей, не роби тиску і не звуч як примус.
- Дай легке підтвердження бажання, але з повагою до комфорту: "якщо ти справді цього хочеш", "без поспіху", "щоб нам обом було комфортно".
- Якщо користувач пише, що він цього хоче, найкращий варіант має приймати пропозицію, а не ставити під сумнів сам факт бажання.
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
- Кожен текст повідомлення у варіантах має бути коротшим за 240 символів.
- Якщо в переписці є явний холод або відмова, поважай це.
- Якщо обрано грубий режим, можна писати простіше, різкіше і з легкою лайкою, але не ображай дівчину, не принижуй її і не тисни.
- Використовуй фрази користувача тільки там, де вони звучать природно.
- Не використовуй фрази-табу.
- Не використовуй Markdown: ніяких ###, **, *, списків із зірочками або декоративних розділювачів.
- Не став повідомлення в кутові лапки «...». Просто пиши текст повідомлення.
- Відповідай саме на останню ситуацію або повідомлення. Не змінюй тему, якщо вона вже дала прямий сигнал.

Мова відповіді: {language}
Ситуація: {situation}
Бажаний тон: {tone}
Ціль: {goal}
Режим спілкування: {communication_mode}
Стиль користувача: {user_style or "простий, природний, без пафосу"}
Фрази користувача, які можна вплітати: {phrase_bank or "немає"}
Фрази-табу, яких треба уникати: {avoid_phrases or "немає"}
{rough_rules}
{intimate_rules}

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
    is_intimate = is_intimate_context(data)

    if is_ua:
        opener = "Мені здається, тут краще написати легко і без тиску."
        if is_intimate:
            opener = "Тут краще відповісти прямо, фліртово і без тиску."
            variants = [
                {
                    "best": "Ого, пропозиція смілива. Я теж цього хочу, якщо ти серйозно. Давай побачимось без зайвого поспіху і зробимо так, щоб нам обом було комфортно.",
                    "softer": "Мені приємно, що ти це запропонувала. Я не проти, просто хочу, щоб нам обом було комфортно і без зайвого поспіху.",
                    "bolder": "Ти вмієш зацікавити. Я за, якщо це справді те, чого ти хочеш.",
                    "funny": "Ну все, ти офіційно зробила вечір цікавішим. Давай тільки без хаосу, домовимось нормально.",
                    "interest": 82,
                },
                {
                    "best": "Якщо чесно, я теж про це думав. Якщо ти справді хочеш згадати старе, я за. Давай зустрінемось і без поспіху зрозуміємо, як нам обом буде добре.",
                    "softer": "Я не проти. Мені важливо тільки, щоб це було не на емоціях, а так, щоб нам обом було спокійно і комфортно.",
                    "bolder": "Я теж хочу. Тільки давай без гри в натяки: якщо ми обоє за, можемо нормально домовитись про зустріч.",
                    "funny": "Ну ти зараз дуже різко зробила переписку цікавішою. Я за, але давай по-дорослому і без хаосу.",
                    "interest": 84,
                },
                {
                    "best": "Ти мене цим зачепила. Я теж не проти, якщо це справді твоє бажання. Давай побачимось і зробимо все спокійно, без тиску.",
                    "softer": "Мені подобається твоя відвертість. Я відкритий до цього, якщо нам обом буде комфортно.",
                    "bolder": "Так, я хочу. Але хочу, щоб це було взаємно і без поспіху, тому давай нормально домовимось.",
                    "funny": "Окей, такий поворот я точно не ігнорую. Я за, якщо ти не передумала.",
                    "interest": 79,
                },
                {
                    "best": "Мені подобається, що ти сказала це прямо. Я теж хочу, але без дурного поспіху: давай зустрінемось і подивимось, як нам буде разом.",
                    "softer": "Я радий, що ти це озвучила. Я не проти, просто хочу, щоб усе було взаємно і комфортно.",
                    "bolder": "Тоді давай без зайвих натяків: я за. Якщо ти теж налаштована серйозно, домовимось про зустріч.",
                    "funny": "Ну все, після такого повідомлення я вже не можу робити вигляд, що просто читаю чат спокійно.",
                    "interest": 87,
                },
            ]
            selected = variants[variant_index(data, len(variants))]
            best = selected["best"]
            softer = selected["softer"]
            bolder = selected["bolder"]
            funny = selected["funny"]
            why = "Відповідь прямо приймає її пропозицію, але залишає простір для взаємного комфорту і не тисне."
            avoid = "Не пиши грубі сексуальні подробиці, не тисни на швидку зустріч і не роби вигляд, що тобі байдуже."
            interest = selected["interest"]
            flirt = "високий"
            mood = "фліртовий"
            recommendation = "сміливіше"
            reply_time = "зараз"
        elif "глухий" in situation.lower() or "мовч" in situation.lower():
            best = "Слухай, я щось згадав нашу розмову і подумав: а який у тебе зараз найприємніший план на тиждень?"
            softer = "До речі, як у тебе день проходить?"
            bolder = "Ти цікава. Хочу краще тебе зрозуміти, розкажеш трохи більше?"
            funny = "Окей, тепер мені потрібна повна версія цієї історії, бо тизер вийшов сильний."
            why = "Повідомлення коротке, не просить уваги силою і дає їй легку тему для відповіді."
            avoid = "Не пиши докори типу \"чого мовчиш\", не засипай повідомленнями і не роби вигляд, що тобі байдуже, якщо це не так."
            interest = 48
            flirt = "низький"
            mood = "нейтральний"
            recommendation = "відповідати спокійно"
            reply_time = "через 5-10 хвилин"
        elif "запрос" in situation.lower() or "зустр" in situation.lower():
            best = "Мені з тобою цікаво спілкуватись. Може, вип'ємо кави цього тижня і продовжимо вже наживо?"
            softer = "Можемо якось спокійно побачитись на каву, якщо тобі теж цікаво."
            bolder = "Давай не затягувати тільки перепискою. Побачимось цього тижня?"
            funny = "Пропоную перевести це з режиму чату в режим кави. Як тобі план?"
            why = "Пропозиція звучить легко, без тиску на конкретний час і дає їй простий спосіб погодитись або перенести."
            avoid = "Не став ультиматуми і не роби зустріч вимогою."
            interest = 58
            flirt = "середній"
            mood = "теплий"
            recommendation = "відповідати спокійно"
            reply_time = "зараз"
        else:
            best = "Ахах, звучить цікаво. А як ти взагалі до цього прийшла?"
            softer = "До речі, як у тебе день проходить?"
            bolder = "Ти цікава. Хочу краще тебе зрозуміти, розкажеш трохи більше?"
            funny = "Окей, тепер мені потрібна повна версія цієї історії, бо тизер вийшов сильний."
            why = "Повідомлення коротке, не просить уваги силою і дає їй легку тему для відповіді."
            avoid = "Не пиши докори, не засипай повідомленнями і не роби вигляд, що тобі байдуже, якщо це не так."
            interest = 48
            flirt = "низький"
            mood = "нейтральний"
            recommendation = "відповідати спокійно"
            reply_time = "через 5-10 хвилин"
        if is_rough:
            opener = "Ок, даю грубіший варіант, але без наїзду."
            if is_intimate:
                opener = "Ок, даю пряміший варіант, але без тиску і бруду."
                rough_variants = [
                    {
                        "best": "Ох, ти вмієш влучити в тему. Я теж цього хочу, якщо ти серйозно. Давай побачимось без дурного поспіху і зробимо все так, щоб нам обом було норм.",
                        "softer": "Мені це подобається. Я не проти, просто хочу, щоб усе було нормально і комфортно для нас обох.",
                        "bolder": "Я за. Тільки давай чесно і по-дорослому: якщо ти справді цього хочеш, зустрінемось і домовимось.",
                        "funny": "Ну все, після такого повідомлення я вже точно не роблю вигляд, що спокійний. Давай тільки без хаосу, нормально домовимось.",
                        "interest": 86,
                    },
                    {
                        "best": "Та ти зараз нормально так підкинула тему. Я за, якщо ти не просто жартуєш. Давай зустрінемось і без зайвого цирку все вирішимо.",
                        "softer": "Мені ок така ідея. Головне, щоб нам обом було комфортно і без тупого поспіху.",
                        "bolder": "Я хочу. Якщо ти теж, давай не гратись у натяки і домовимось нормально.",
                        "funny": "Ну капець, спокійний вечір уже скасовано. Я за, якщо ти серйозно.",
                        "interest": 88,
                    },
                    {
                        "best": "Оце поворот. Я теж хочу, але давай по-нормальному: зустрінемось, без тиску, і дивимось по відчуттях.",
                        "softer": "Я не проти. Просто хочу, щоб це було взаємно, а не на дурних емоціях.",
                        "bolder": "Я за. Кажи, коли тобі норм побачитись, і домовимось без зайвої драми.",
                        "funny": "Ти вмієш зламати мені план бути спокійним. Я за, якщо ти справді цього хочеш.",
                        "interest": 83,
                    },
                ]
                selected = rough_variants[variant_index(data, len(rough_variants))]
                best = selected["best"]
                softer = selected["softer"]
                bolder = selected["bolder"]
                funny = selected["funny"]
                why = "Відповідь звучить пряміше, але не переходить у тиск або брудний текст."
                avoid = "Не пиши принизливих або надто графічних фраз і не вимагай зустрічі прямо зараз."
                interest = selected["interest"]
                flirt = "високий"
                mood = "провокативний"
                recommendation = "сміливіше"
                reply_time = "зараз"
            elif "глухий" in situation.lower() or "мовч" in situation.lower():
                best = "Та блін, згадав нашу розмову. Як у тебе там життя, який план на тиждень?"
            elif "запрос" in situation.lower() or "зустр" in situation.lower():
                best = "Слухай, досить оце тільки переписуватись. Погнали на каву цього тижня?"
            else:
                best = "Ахах, ну це вже цікаво. Давай повну версію, бо я тепер не відчеплюсь."
        if phrase_bank and not is_intimate:
            best = f"{best}\n\nМожна з твоєю фразою: {phrase_bank.splitlines()[0][:120]}"
        return f"""{opener}

AI-аналіз:
Зацікавленість: {interest}
Флірт: {flirt}
Настрій: {mood}
Рекомендація: {recommendation}
Коли відповідати: {reply_time}

1. Найкращий варіант:
{best}

2. Ще варіанти:
М'якше: {softer}
Сміливіше: {bolder}
З гумором: {funny}

3. Чому це працює:
{why}

4. Що не варто писати:
{avoid}

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
    model = model or "gemini-3.5-flash"
    generation_config = {
        "temperature": 0.8,
        "maxOutputTokens": 2048,
    }

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


def analyze_screenshot(image_base64, mime_type="image/jpeg"):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Для розпізнавання скріншотів потрібен GEMINI_API_KEY.")
    if mime_type not in ("image/jpeg", "image/png", "image/webp"):
        raise ValueError("Підтримуються JPG, PNG і WEBP.")

    try:
        raw = base64.b64decode(image_base64, validate=True)
    except Exception as error:
        raise ValueError("Не вдалося прочитати файл зображення.") from error
    if len(raw) > 7 * 1024 * 1024:
        raise ValueError("Скріншот завеликий. Максимум 7 МБ.")

    prompt = """
Розпізнай переписку на скріншоті месенджера.
Визнач автора за розташуванням бульбашок: повідомлення власника акаунта зазвичай праворуч,
повідомлення співрозмовниці зазвичай ліворуч. Врахуй підписи, кольори та цитати.
Поверни тільки повідомлення у хронологічному порядку, по одному на рядок:
Я: текст
Вона: текст
Не додавай порад, аналізу, Markdown або вигаданих слів.
Якщо сторону неможливо визначити, напиши Невідомо: текст.
""".strip()
    errors = []
    for attempt in range(2):
        if attempt:
            time.sleep(2)
        for model in gemini_model_candidates():
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": image_base64,
                                }
                            },
                        ]
                    }
                ],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1600},
            }
            try:
                result = post_json(
                    GEMINI_URL_TEMPLATE.format(model=model, api_key=api_key),
                    payload,
                    {"Content-Type": "application/json"},
                )
                chunks = [
                    part.get("text", "")
                    for candidate in result.get("candidates", [])
                    for part in candidate.get("content", {}).get("parts", [])
                ]
                transcript = "\n".join(chunks).strip()
                if transcript:
                    return {"transcript": transcript, "mode": f"Gemini Vision: {model}"}
            except Exception as error:
                errors.append(str(error))
    reason = short_error(errors[-1] if errors else "empty response")
    raise RuntimeError(f"{reason} Спробуй ще раз через хвилину.")


def conversation_owner_for_user(user):
    return f"site:{user['id']}"


def add_history_to_prompt(data, user):
    conversation_key = str(data.get("conversationKey", "")).strip()
    new_message = str(data.get("newMessage", "")).strip()
    if not conversation_key or not new_message:
        return data

    owner_key = conversation_owner_for_user(user)
    add_conversation_message(
        owner_key,
        conversation_key,
        data.get("personName", ""),
        data.get("speaker", "Вона"),
        new_message,
        "site",
    )
    history = list_conversation_messages(owner_key, conversation_key, limit=40)
    transcript = "\n".join(f"{item['speaker']}: {item['content']}" for item in history)
    enriched = dict(data)
    notes = str(data.get("context", "")).strip()
    enriched["context"] = (
        f"Збережена історія переписки з {data.get('personName') or 'цією людиною'}:\n"
        f"{transcript}\n\n"
        f"Додатковий контекст:\n{notes or 'немає'}\n\n"
        "Запропонуй відповідь саме на останнє повідомлення з цієї історії."
    )
    return enriched


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
        seen = set()
        errors = []
        for model in gemini_model_candidates():
            if not model or model in seen:
                continue
            seen.add(model)
            try:
                result = call_gemini(data, model)
                if not is_empty_model_reply(result.get("text", "")):
                    return result
                errors.append(f"{model}: empty response")
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
            result = call_openrouter(data)
            if not is_empty_model_reply(result.get("text", "")):
                return result
            raise RuntimeError("empty response")
        except Exception as error:
            return {
                "text": f"OpenRouter зараз не відповів нормально, тому даю локальну підказку.\n\n{short_error(error)}\n\n{fallback_reply(data)}",
                "mode": "OpenRouter недоступний",
            }
    if os.getenv("OPENAI_API_KEY", "").strip():
        try:
            result = call_openai(data)
            if not is_empty_model_reply(result.get("text", "")):
                return result
            raise RuntimeError("empty response")
        except Exception as error:
            return {
                "text": f"OpenAI зараз не відповів нормально, тому даю локальну підказку.\n\n{short_error(error)}\n\n{fallback_reply(data)}",
                "mode": "OpenAI недоступний",
            }
    return {"text": fallback_reply(data), "mode": "Локальний режим"}


def is_empty_model_reply(text):
    message = str(text or "").strip().lower()
    if not message:
        return True
    return (
        "не вдалося прочитати відповідь" in message
        or "не вдалося прочитати відповідь gemini" in message
        or "не вдалося прочитати відповідь openrouter" in message
        or "не вдалося прочитати відповідь моделі" in message
    )


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
        if path == "/admin":
            self.serve_index()
            return
        if path == "/api/me":
            self.handle_me()
            return
        if path == "/api/admin/history":
            self.handle_history()
            return
        if path == "/api/admin/users":
            self.handle_users()
            return
        if path == "/api/conversation":
            self.handle_conversation()
            return
        if path == "/api/conversations":
            self.handle_conversations()
            return
        super().do_GET()

    def serve_index(self):
        try:
            with open("index.html", "rb") as file:
                body = file.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            self.send_error(404)

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
        if self.path == "/api/analyze-screenshot":
            self.handle_screenshot()
            return
        if self.path == "/api/conversation/clear":
            self.handle_clear_conversation()
            return
        if self.path == "/api/suggest":
            self.handle_suggest()
            return
        self.send_error(404)

    def handle_suggest(self):
        try:
            user = self.current_user()
            if not user:
                self.send_json(401, {"error": "Спочатку зареєструйся або увійди в акаунт."})
                return
            data = self.read_json()
            enriched_data = add_history_to_prompt(data, user)
            result = suggest(enriched_data)
            log_interaction(
                "site",
                enriched_data.get("context", ""),
                result.get("text", ""),
                result.get("mode", ""),
                user=user,
                display_name=user["name"] if user else "Гість",
            )
            self.send_json(200, result)
        except Exception as error:
            self.send_json(500, {"error": str(error)})

    def handle_screenshot(self):
        user = self.current_user()
        if not user:
            self.send_json(401, {"error": "Спочатку увійди в акаунт."})
            return
        try:
            data = self.read_json(max_bytes=10 * 1024 * 1024)
            image = str(data.get("image", ""))
            if "," in image and image.startswith("data:"):
                image = image.split(",", 1)[1]
            self.send_json(
                200,
                analyze_screenshot(image, data.get("mime_type", "image/jpeg")),
            )
        except (ValueError, RuntimeError) as error:
            self.send_json(400, {"error": str(error)})
        except Exception:
            self.send_json(500, {"error": "Не вдалося розпізнати скріншот. Спробуй інше зображення."})

    def handle_conversation(self):
        user = self.current_user()
        if not user:
            self.send_json(401, {"error": "Спочатку увійди в акаунт."})
            return
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        conversation_key = query.get("conversation_key", [""])[0].strip()
        if not conversation_key:
            self.send_json(400, {"error": "Обери профіль співрозмовниці."})
            return
        items = list_conversation_messages(
            conversation_owner_for_user(user),
            conversation_key,
            limit=60,
        )
        self.send_json(200, {"items": items})

    def handle_conversations(self):
        user = self.current_user()
        if not user:
            self.send_json(401, {"error": "Спочатку увійди в акаунт."})
            return
        self.send_json(
            200,
            {"items": list_conversations(conversation_owner_for_user(user))},
        )

    def handle_clear_conversation(self):
        user = self.current_user()
        if not user:
            self.send_json(401, {"error": "Спочатку увійди в акаунт."})
            return
        conversation_key = str(self.read_json().get("conversation_key", "")).strip()
        if not conversation_key:
            self.send_json(400, {"error": "Обери профіль співрозмовниці."})
            return
        clear_conversation_messages(conversation_owner_for_user(user), conversation_key)
        self.send_json(200, {"ok": True})

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

    def read_json(self, max_bytes=1024 * 1024):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        if length > max_bytes:
            raise ValueError("Запит завеликий.")
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
