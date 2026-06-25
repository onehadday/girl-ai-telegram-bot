const fields = {
  situation: document.querySelector("#situation"),
  tone: document.querySelector("#tone"),
  language: document.querySelector("#language"),
  goal: document.querySelector("#goal"),
  style: document.querySelector("#style"),
  communicationMode: document.querySelector("#communicationMode"),
  phraseBank: document.querySelector("#phraseBank"),
  avoidPhrases: document.querySelector("#avoidPhrases"),
  context: document.querySelector("#context"),
  personProfile: document.querySelector("#personProfile"),
};

const messages = document.querySelector("#messages");
const generateBtn = document.querySelector("#generateBtn");
const loginBtn = document.querySelector("#loginBtn");
const logoutBtn = document.querySelector("#logoutBtn");
const saveProfileBtn = document.querySelector("#saveProfileBtn");
const modeBadge = document.querySelector("#modeBadge");
const authStatus = document.querySelector("#authStatus");
const registerForm = document.querySelector("#registerForm");
const loginForm = document.querySelector("#loginForm");
const registerStatus = document.querySelector("#registerStatus");
const loginStatus = document.querySelector("#loginStatus");
const changePasswordForm = document.querySelector("#changePasswordForm");
const refreshUsersBtn = document.querySelector("#refreshUsersBtn");
const adminPasswordForm = document.querySelector("#adminPasswordForm");
const toggleNewPasswordBtn = document.querySelector("#toggleNewPasswordBtn");
const toggleAdminPasswordBtn = document.querySelector("#toggleAdminPasswordBtn");
const adminUsers = document.querySelector("#adminUsers");
const adminHistory = document.querySelector("#adminHistory");
const selectedUserTitle = document.querySelector("#selectedUserTitle");
const selectedUserHint = document.querySelector("#selectedUserHint");
const personForm = document.querySelector("#personForm");
const personStatusText = document.querySelector("#personStatusText");
const peopleList = document.querySelector("#peopleList");
const favoritesList = document.querySelector("#favoritesList");

let currentUser = null;
let selectedAdminUser = null;
let lastPayload = null;
let lastResponseText = "";

function cleanMarkdown(text) {
  return String(text || "")
    .replace(/\r/g, "")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/[«»]/g, "")
    .replace(/^\s*-{3,}\s*$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function uid() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function userKey(name) {
  if (!currentUser) return null;
  const id = currentUser.id || currentUser.email || "guest";
  return `girlAi:${id}:${name}`;
}

function readUserStore(name, fallback) {
  const key = userKey(name);
  if (!key) return fallback;
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeUserStore(name, value) {
  const key = userKey(name);
  if (!key) return;
  localStorage.setItem(key, JSON.stringify(value));
}

function getPeople() {
  return readUserStore("people", []);
}

function savePeople(people) {
  writeUserStore("people", people);
  renderPeople();
  renderProfileSelect();
}

function getFavorites() {
  return readUserStore("favorites", []);
}

function saveFavorites(items) {
  writeUserStore("favorites", items);
  renderFavorites();
}

function getSelectedPerson() {
  const id = fields.personProfile.value;
  if (!id) return null;
  return getPeople().find((person) => person.id === id) || null;
}

function personSummary(person) {
  if (!person) return "";
  const parts = [
    person.name && `Ім'я: ${person.name}`,
    person.age && `Вік: ${person.age}`,
    person.style && `Стиль спілкування: ${person.style}`,
    person.likes && `Подобається: ${person.likes}`,
    person.dislikes && `Не подобається: ${person.dislikes}`,
    person.facts && `Важливі факти: ${person.facts}`,
    person.status && `Статус: ${person.status}`,
  ].filter(Boolean);
  return parts.join("\n");
}

function collectPayload(extraInstruction = "") {
  const payload = Object.fromEntries(
    Object.entries(fields)
      .filter(([key]) => key !== "personProfile")
      .map(([key, input]) => [key, input.value.trim()])
  );
  const selectedPerson = getSelectedPerson();
  const profileText = personSummary(selectedPerson);
  const additions = [];

  if (profileText) {
    additions.push(`Профіль співрозмовниці, який треба врахувати:\n${profileText}`);
  }
  additions.push("Форматуй відповідь чисто, без Markdown-символів ###, ** або списків з зірочками.");
  additions.push("Режим грубуватого стилю має бути впевненим і живим, але без принижень, погроз, тиску та маніпуляцій.");
  if (extraInstruction) additions.push(extraInstruction);

  payload.context = [payload.context, additions.join("\n")].filter(Boolean).join("\n\n");
  payload.selectedProfile = profileText;
  return payload;
}

function setBusy(isBusy) {
  generateBtn.disabled = isBusy;
  generateBtn.textContent = isBusy ? "Думаю..." : "Підібрати відповідь";
  modeBadge.textContent = isBusy ? "працюю" : "готовий";
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function apiJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Помилка запиту");
  return data;
}

async function requestSuggestion(payload) {
  const delays = [0, 1800, 4200];
  let lastError;

  for (let attempt = 0; attempt < delays.length; attempt += 1) {
    if (delays[attempt]) {
      addMessage("assistant", "Сервер прокидається після паузи. Пробую ще раз...");
      await wait(delays[attempt]);
    }

    try {
      return await apiJson("/api/suggest", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

function firstSentence(text, max = 120) {
  const cleaned = cleanMarkdown(text).replace(/\s+/g, " ");
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, max).trim()}...`;
}

function extractSection(text, startWords, endWords = []) {
  const cleaned = cleanMarkdown(text);
  const startPattern = startWords.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const endPattern = endWords.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const regex = endPattern
    ? new RegExp(`(?:${startPattern})[:\\s]*([\\s\\S]*?)(?=\\n\\s*(?:${endPattern})[:\\s]|$)`, "i")
    : new RegExp(`(?:${startPattern})[:\\s]*([\\s\\S]*)`, "i");
  const match = cleaned.match(regex);
  return match ? match[1].trim() : "";
}

function extractVariants(text) {
  const cleaned = cleanMarkdown(text);
  const lines = cleaned.split("\n").map((line) => line.trim()).filter(Boolean);
  const sections = {};
  let currentKey = "";

  for (const line of lines) {
    const normalized = line
      .toLowerCase()
      .replace(/[’']/g, "")
      .replace(/[:№\d.\s]+$/g, "")
      .trim();
    const directKey =
      normalized.includes("найкращий варіант") || normalized.includes("best message") ? "best" :
      normalized === "мякше" || normalized.includes("softer") ? "soft" :
      normalized === "сміливіше" || normalized.includes("bolder") ? "bold" :
      normalized === "з гумором" || normalized.includes("funny") ? "funny" :
      normalized.includes("ще варіанти") || normalized.includes("чому це працює") || normalized.includes("що не варто") || normalized.includes("попередження") ? "stop" :
      "";

    if (directKey) {
      currentKey = directKey === "stop" ? "" : directKey;
      if (currentKey && !sections[currentKey]) sections[currentKey] = "";
      const afterColon = line.includes(":") ? line.split(":").slice(1).join(":").trim() : "";
      if (currentKey && afterColon) sections[currentKey] = [sections[currentKey], afterColon].filter(Boolean).join(" ");
      continue;
    }

    if (currentKey) {
      sections[currentKey] = [sections[currentKey], line].filter(Boolean).join(" ");
    }
  }

  const pick = (labels, stops) => {
    const labelPattern = labels.join("|");
    const stopPattern = stops.join("|");
    const regex = new RegExp(`(?:${labelPattern})\\s*:?\\s*([\\s\\S]*?)(?=(?:\\n|\\s)+(?:${stopPattern})\\s*:?|$)`, "i");
    const match = cleaned.match(regex);
    return match ? cleanMarkdown(match[1]).replace(/^[:\s]+/, "").trim() : "";
  };

  const bestSection = pick(
    ["Найкращий варіант", "Best message"],
    ["Ще варіанти", "М['’]?якше", "Сміливіше", "З гумором", "Чому це працює", "Що не варто писати", "Попередження", "Avoid"]
  ) || extractSection(cleaned, ["Найкращий варіант", "Best message"], ["Ще варіанти", "Чому це працює", "Що не варто писати", "Попередження"]);
  const softSection = pick(["М['’]?якше", "Softer"], ["Сміливіше", "З гумором", "Чому це працює", "Що не варто писати", "Попередження", "Avoid"]);
  const boldSection = pick(["Сміливіше", "Bolder"], ["З гумором", "Чому це працює", "Що не варто писати", "Попередження", "Avoid"]);
  const funnySection = pick(["З гумором", "Funny"], ["Чому це працює", "Що не варто писати", "Попередження", "Avoid"]);
  const firstQuoted = cleaned.match(/["“](.+?)["”]/);
  const paragraphs = cleaned
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter((part) => part && !/^(ось варіанти|ще варіанти|чому це працює|що не варто писати|попередження)[:\s]*$/i.test(part));
  const fallback = firstQuoted ? firstQuoted[1] : paragraphs[0] || cleaned;

  const variants = [
    { key: "best", icon: "🏆", title: "Найкращий варіант", text: bestSection || sections.best || fallback },
    { key: "soft", icon: "😊", title: "М'якше", text: softSection || sections.soft || "" },
    { key: "bold", icon: "🔥", title: "Сміливіше", text: boldSection || sections.bold || "" },
    { key: "funny", icon: "😂", title: "З гумором", text: funnySection || sections.funny || "" },
  ];

  const extraParagraphs = paragraphs.filter((part) => {
    const compact = part.toLowerCase();
    return part.length < 320
      && !compact.includes("чому це працює")
      && !compact.includes("що не варто")
      && !variants.some((item) => item.text && part.includes(item.text));
  });
  for (const item of variants) {
    if (!item.text && extraParagraphs.length) item.text = extraParagraphs.shift();
  }

  return variants.filter((item) => item.text).map((item) => ({
    ...item,
    text: cleanMarkdown(item.text).replace(/^[:\s]+/, ""),
  }));
}

function analyzePayload(payload) {
  const text = payload.context || "";
  const compact = text.toLowerCase();
  let interest = 45;
  if (text.length > 80) interest += 12;
  if (/[?？]/.test(text)) interest += 12;
  if (/(ахах|хаха|😂|🙂|\)|😉)/i.test(text)) interest += 10;
  if (/(ок|ясно|дякую|спс|угу)$/i.test(compact.trim())) interest -= 12;
  if (/(не хочу|відстань|не пиши|занята|зайнята)/i.test(compact)) interest -= 18;
  interest = Math.max(8, Math.min(92, interest));

  const flirt = /(флірт|побачення|кава|зустріч|красива|подоба)/i.test(compact)
    ? "середній"
    : interest > 70
      ? "середній"
      : "низький";
  const mood = interest > 75 ? "теплий" : interest < 35 ? "холодний" : flirt === "середній" ? "фліртовий" : "нейтральний";
  const recommendation = interest < 35
    ? "не поспішати"
    : payload.tone && payload.tone.includes("гумор")
      ? "з гумором"
      : payload.situation && payload.situation.includes("зустріч")
        ? "сміливіше"
        : "відповідати спокійно";
  const timing = interest < 35
    ? "краще не відповідати одразу"
    : payload.situation && payload.situation.includes("давно не відповідає")
      ? "через 20-30 хвилин"
      : payload.situation && payload.situation.includes("глухий кут")
        ? "через 5-10 хвилин"
        : "зараз";

  return { interest, flirt, mood, recommendation, timing };
}

function buildCoach(payload, responseText) {
  const score = payload.context.length > 120 ? "A" : "B+";
  const mode = payload.communicationMode || "Нормальний";
  return {
    score,
    strengths: [
      "Відповідь не тисне і залишає простір для діалогу.",
      mode.includes("бидла") ? "Стиль живий і різкіший, але без переходу на приниження." : "Тон виглядає природно і без зайвого пафосу.",
    ],
    mistakes: [
      "Не засипай її кількома питаннями підряд.",
      "Не пояснюй занадто довго, якщо вона відповідає коротко.",
    ],
    advice: responseText.length > 700
      ? "Вибери один короткий варіант і не відправляй весь текст одразу."
      : "Після її відповіді підхопи одну деталь, а не починай тему з нуля.",
  };
}

function buildRedFlags(payload) {
  const items = ["Не пиши з претензією, якщо вона відповіла коротко.", "Не проси пояснень одразу, це може виглядати нав'язливо."];
  if ((payload.communicationMode || "").includes("бидла")) items.push("Мат може бути тільки як стиль, не як образа в її сторону.");
  if ((payload.situation || "").includes("зустріч")) items.push("Запрошення краще робити легким, без тиску на конкретний час.");
  return items.slice(0, 4);
}

function collapsible(title, preview, bodyHtml) {
  return `
    <details class="insight-card">
      <summary>
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(preview)}</span>
      </summary>
      <div class="insight-body">${bodyHtml}</div>
    </details>
  `;
}

function renderAssistantResult(text, payload) {
  const cleaned = cleanMarkdown(text);
  const variants = extractVariants(cleaned);
  const analysis = analyzePayload(payload || lastPayload || {});
  const redFlags = buildRedFlags(payload || lastPayload || {});
  const coach = buildCoach(payload || lastPayload || {}, cleaned);
  const why = extractSection(cleaned, ["Чому це працює", "Why it works"], ["Що не варто писати", "Попередження", "Avoid"]);
  const avoid = extractSection(cleaned, ["Що не варто писати", "Попередження", "Avoid"], []);

  const article = document.createElement("article");
  article.className = "message assistant result-message";
  article.innerHTML = `
    <span>AI</span>
    <div class="analysis-card">
      <div>
        <p class="eyebrow">AI-аналіз</p>
        <h3>${analysis.interest}% зацікавленості</h3>
      </div>
      <div class="analysis-grid">
        <div><strong>${escapeHtml(analysis.flirt)}</strong><small>рівень флірту</small></div>
        <div><strong>${escapeHtml(analysis.mood)}</strong><small>настрій</small></div>
        <div><strong>${escapeHtml(analysis.recommendation)}</strong><small>рекомендація</small></div>
        <div><strong>${escapeHtml(analysis.timing)}</strong><small>коли відповісти</small></div>
      </div>
    </div>

    <div class="result-grid">
      ${variants.map((item) => `
        <section class="result-card" data-answer="${escapeHtml(item.text)}">
          <div class="result-title"><span>${item.icon}</span><strong>${escapeHtml(item.title)}</strong></div>
          <p>${escapeHtml(item.text)}</p>
          <div class="card-actions">
            <button class="copy-answer" type="button">Скопіювати</button>
            <button class="favorite-answer secondary" type="button">В обране</button>
          </div>
        </section>
      `).join("")}
    </div>

    <div class="result-actions">
      <button class="regenerate-answer" type="button">🎲 Згенерувати ще</button>
      <span>Оціни відповідь</span>
      <button class="rate-answer secondary" data-rate="like" type="button">👍 Сподобалось</button>
      <button class="rate-answer secondary" data-rate="dislike" type="button">👎 Не підійшло</button>
      <button class="retry-different hidden" type="button">Спробувати по-іншому</button>
    </div>

    <div class="insights">
      ${collapsible("🚩 На що звернути увагу", redFlags[0] || "короткі підказки по тону", `<ul>${redFlags.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`)}
      ${collapsible("🎓 Оцінка переписки", `Оцінка ${coach.score}`, `
        <p><strong>Оцінка:</strong> ${escapeHtml(coach.score)}</p>
        <p><strong>Сильні сторони:</strong> ${escapeHtml(coach.strengths.join(" "))}</p>
        <p><strong>Можливі помилки:</strong> ${escapeHtml(coach.mistakes.join(" "))}</p>
        <p><strong>Порада:</strong> ${escapeHtml(coach.advice)}</p>
      `)}
      ${why ? collapsible("Чому це працює", firstSentence(why, 90), `<p>${escapeHtml(why)}</p>`) : ""}
      ${avoid ? collapsible("Що не варто писати", firstSentence(avoid, 90), `<p>${escapeHtml(avoid)}</p>`) : ""}
    </div>
  `;
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

function addMessage(role, text, payload = null) {
  if (role === "assistant" && payload) {
    renderAssistantResult(text, payload);
    return;
  }

  const article = document.createElement("article");
  article.className = `message ${role}`;
  const safeText = cleanMarkdown(text)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => `<p>${escapeHtml(line)}</p>`)
    .join("");
  article.innerHTML = `<span>${role === "user" ? "Ти" : "AI"}</span>${safeText}`;
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

function saveLocalSettings() {
  const data = {
    style: fields.style.value,
    phraseBank: fields.phraseBank.value,
    avoidPhrases: fields.avoidPhrases.value,
    communicationMode: fields.communicationMode.value,
    profileName: document.querySelector("#profileName").value,
    profileAbout: document.querySelector("#profileAbout").value,
  };
  writeUserStore("settings", data);
}

function loadLocalSettings() {
  const data = readUserStore("settings", {});
  for (const key of ["style", "phraseBank", "avoidPhrases", "communicationMode"]) {
    if (data[key] && fields[key]) fields[key].value = data[key];
  }
  document.querySelector("#profileName").value = data.profileName || "";
  document.querySelector("#profileAbout").value = data.profileAbout || "";
}

function clearSessionUi() {
  selectedAdminUser = null;
  lastPayload = null;
  lastResponseText = "";
  sessionStorage.clear();
  messages.innerHTML = `
    <article class="message assistant">
      <span>AI</span>
      <p>Спочатку зареєструйся або увійди в кабінеті. Після цього кидай переписку або опис ситуації, і я дам варіанти відповіді.</p>
    </article>
  `;
  adminUsers.textContent = "Увійди під адміном і натисни “Оновити”.";
  adminHistory.textContent = "Історія з'явиться тут.";
  peopleList.textContent = "Профілі з'являться тут.";
  favoritesList.textContent = "Обрані відповіді з'являться тут.";
  fields.personProfile.innerHTML = '<option value="">Без профілю</option>';
}

function clearAuthForms() {
  registerForm.reset();
  loginForm.reset();
  setFormStatus(registerStatus, "", "info");
  setFormStatus(loginStatus, "", "info");
}

function updateAuthUi(user) {
  currentUser = user;
  document.querySelectorAll("[data-admin-only='true']").forEach((item) => {
    item.classList.toggle("hidden", !user || !user.is_admin);
  });

  if (user) {
    authStatus.textContent = user.is_admin ? `${user.name} · адмін` : user.name;
    loginBtn.classList.add("hidden");
    logoutBtn.classList.remove("hidden");
    loadLocalSettings();
    renderPeople();
    renderProfileSelect();
    renderFavorites();
  } else {
    authStatus.textContent = "гість";
    loginBtn.classList.remove("hidden");
    logoutBtn.classList.add("hidden");
    if (document.querySelector("#view-admin").classList.contains("active")) showView("chat");
  }
}

async function refreshMe() {
  try {
    const data = await apiJson("/api/me");
    updateAuthUi(data.user);
  } catch {
    updateAuthUi(null);
  }
}

function showView(name) {
  if (name === "admin" && (!currentUser || !currentUser.is_admin)) name = "chat";
  document.querySelectorAll(".nav-btn").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === name);
  });
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  document.querySelector(`#view-${name}`).classList.add("active");
}

function togglePassword(inputId, button) {
  const input = document.querySelector(inputId);
  const isPassword = input.type === "password";
  input.type = isPassword ? "text" : "password";
  button.textContent = isPassword ? "Сховати" : "Показати";
}

function setFormStatus(element, text, type = "info") {
  element.textContent = text || "";
  element.className = `form-status ${type}`;
}

function setSubmitBusy(form, isBusy, busyText) {
  const button = form.querySelector('button[type="submit"]');
  if (!button) return;
  if (!button.dataset.defaultText) button.dataset.defaultText = button.textContent;
  button.disabled = isBusy;
  button.textContent = isBusy ? busyText : button.dataset.defaultText;
}

function renderProfileSelect() {
  const people = getPeople();
  const selected = fields.personProfile.value;
  fields.personProfile.innerHTML = '<option value="">Без профілю</option>' + people.map((person) => (
    `<option value="${escapeHtml(person.id)}">${escapeHtml(person.name || "Без імені")} · ${escapeHtml(person.status || "профіль")}</option>`
  )).join("");
  if (people.some((person) => person.id === selected)) fields.personProfile.value = selected;
}

function renderPeople() {
  const people = getPeople();
  if (!currentUser) {
    peopleList.textContent = "Увійди, щоб бачити свої профілі.";
    return;
  }
  if (!people.length) {
    peopleList.innerHTML = '<div class="empty-card">Поки немає профілів. Додай перший, і відповіді стануть точнішими.</div>';
    return;
  }
  peopleList.innerHTML = people.map((person) => `
    <article class="person-card">
      <div>
        <h3>${escapeHtml(person.name || "Без імені")}</h3>
        <p>${escapeHtml([person.age && `${person.age} років`, person.status, person.style].filter(Boolean).join(" · "))}</p>
      </div>
      <details>
        <summary>Деталі</summary>
        <p>${escapeHtml(personSummary(person))}</p>
      </details>
      <div class="card-actions">
        <button class="use-person" data-id="${escapeHtml(person.id)}" type="button">Використати</button>
        <button class="delete-person secondary" data-id="${escapeHtml(person.id)}" type="button">Видалити</button>
      </div>
    </article>
  `).join("");
}

function renderFavorites() {
  const favorites = getFavorites();
  if (!currentUser) {
    favoritesList.textContent = "Увійди, щоб бачити своє обране.";
    return;
  }
  if (!favorites.length) {
    favoritesList.innerHTML = '<div class="empty-card">Тут будуть відповіді, які ти додаси в обране.</div>';
    return;
  }
  favoritesList.innerHTML = favorites.map((item) => `
    <article class="favorite-card">
      <div class="history-meta">
        <span>${escapeHtml(item.createdAt || "")}</span>
        <span>${escapeHtml(item.profile || "без профілю")}</span>
      </div>
      <p>${escapeHtml(item.text)}</p>
      <div class="card-actions">
        <button class="copy-favorite" data-id="${escapeHtml(item.id)}" type="button">Скопіювати</button>
        <button class="delete-favorite secondary" data-id="${escapeHtml(item.id)}" type="button">Видалити</button>
      </div>
    </article>
  `).join("");
}

async function copyText(text, button) {
  await navigator.clipboard.writeText(text);
  const oldText = button.textContent;
  button.textContent = "Скопійовано";
  button.classList.add("success");
  await wait(900);
  button.textContent = oldText;
  button.classList.remove("success");
}

async function runSuggestion(extraInstruction = "") {
  const payload = collectPayload(extraInstruction);
  if (!currentUser) {
    addMessage("assistant", "Спочатку зареєструйся або увійди в Кабінеті. Без акаунта сайт не надсилає повідомлення.");
    showView("profile");
    return;
  }
  if (!fields.context.value.trim()) {
    addMessage("assistant", "Додай переписку або короткий опис ситуації. Без контексту порада буде занадто загальна.");
    return;
  }

  saveLocalSettings();
  lastPayload = payload;
  addMessage("user", fields.context.value.trim());
  setBusy(true);

  try {
    const data = await requestSuggestion(payload);
    lastResponseText = data.text || "";
    addMessage("assistant", data.text, payload);
    modeBadge.textContent = data.mode || "готовий";
  } catch (error) {
    addMessage("assistant", `Не вийшло отримати відповідь.\n\nСпробуй ще раз через 20-30 секунд. На безкоштовному Render сервер іноді засинає.\n\nТехнічно: ${error.message}`);
    modeBadge.textContent = "помилка";
  } finally {
    setBusy(false);
  }
}

async function loadAdminUsers() {
  if (!currentUser || !currentUser.is_admin) {
    adminUsers.textContent = "Цей розділ доступний тільки адміну.";
    return;
  }

  adminUsers.textContent = "Завантажую юзерів...";
  adminHistory.textContent = "Обери юзера зліва.";
  adminPasswordForm.classList.add("hidden");
  selectedAdminUser = null;

  try {
    const data = await apiJson("/api/admin/users");
    if (!data.users.length) {
      adminUsers.textContent = "Юзерів поки немає.";
      return;
    }

    adminUsers.innerHTML = data.users
      .map((user) => {
        const label = user.kind === "telegram" ? "Telegram" : user.is_admin ? "Сайт · адмін" : "Сайт";
        const name = user.name || user.email || "Користувач";
        const sub = user.email || `ID: ${user.id}`;
        return `
          <button class="user-card" data-kind="${escapeHtml(user.kind)}" data-id="${escapeHtml(user.id)}">
            <strong>${escapeHtml(name)}</strong>
            <span>${escapeHtml(label)} · ${escapeHtml(sub)}</span>
            <span>${Number(user.messages_count || 0)} повідомлень · ${escapeHtml(user.last_seen || "ще не писав")}</span>
          </button>
        `;
      })
      .join("");

    document.querySelectorAll(".user-card").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".user-card").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        selectedAdminUser = data.users.find(
          (user) => String(user.id) === button.dataset.id && user.kind === button.dataset.kind
        );
        selectedUserTitle.textContent = selectedAdminUser.name || selectedAdminUser.email || "Користувач";
        selectedUserHint.textContent = selectedAdminUser.kind === "telegram"
          ? "Telegram-користувач. Пароль змінити не можна."
          : selectedAdminUser.email;
        adminPasswordForm.classList.toggle("hidden", selectedAdminUser.kind !== "site");
        loadAdminHistory();
      });
    });
  } catch (error) {
    adminUsers.textContent = error.message;
  }
}

async function loadAdminHistory() {
  if (!selectedAdminUser) {
    adminHistory.textContent = "Обери юзера зліва.";
    return;
  }

  adminHistory.textContent = "Завантажую історію...";
  try {
    const params = new URLSearchParams();
    if (selectedAdminUser.kind === "site") {
      params.set("user_id", selectedAdminUser.id);
    } else {
      params.set("source", "telegram");
      params.set("external_id", selectedAdminUser.id);
    }

    const data = await apiJson(`/api/admin/history?${params.toString()}`);
    if (!data.items.length) {
      adminHistory.textContent = "У цього юзера історія поки порожня.";
      return;
    }

    adminHistory.innerHTML = data.items
      .map((item) => {
        const prompt = cleanMarkdown(item.prompt || "");
        const response = cleanMarkdown(item.response || "");
        return `
          <details class="history-item">
            <summary>
              <strong>Що написали: ${escapeHtml(firstSentence(prompt, 85))}</strong>
              <span>${escapeHtml(item.created_at || "")} · ${escapeHtml(item.source || "")} · ${escapeHtml(item.mode || "")}</span>
            </summary>
            <div class="history-body">
              <h4>Повний запит</h4>
              <p>${escapeHtml(prompt)}</p>
              <h4>Відповідь AI</h4>
              <p>${escapeHtml(response)}</p>
            </div>
          </details>
        `;
      })
      .join("");
  } catch (error) {
    adminHistory.textContent = error.message;
  }
}

document.querySelectorAll(".nav-btn").forEach((button) => {
  button.addEventListener("click", () => {
    showView(button.dataset.view);
    if (button.dataset.view === "admin") loadAdminUsers();
    if (button.dataset.view === "favorites") renderFavorites();
    if (button.dataset.view === "people") renderPeople();
  });
});

document.querySelectorAll(".scenario-card").forEach((card) => {
  card.addEventListener("click", () => {
    fields.situation.value = card.dataset.situation;
    fields.goal.value = card.dataset.goal;
    showView("chat");
    fields.context.focus();
  });
});

generateBtn.addEventListener("click", () => runSuggestion());

messages.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;

  if (button.classList.contains("copy-answer")) {
    const card = button.closest(".result-card");
    await copyText(card.dataset.answer || card.innerText, button);
  }

  if (button.classList.contains("favorite-answer")) {
    const card = button.closest(".result-card");
    const selectedPerson = getSelectedPerson();
    const item = {
      id: uid(),
      text: card.dataset.answer || "",
      profile: selectedPerson ? selectedPerson.name : "без профілю",
      createdAt: new Date().toLocaleString("uk-UA"),
    };
    saveFavorites([item, ...getFavorites()]);
    button.textContent = "В обраному";
    button.classList.add("success");
  }

  if (button.classList.contains("regenerate-answer")) {
    await runSuggestion("Дай інші варіанти відповіді. Не повторюй попередні формулювання.");
  }

  if (button.classList.contains("rate-answer")) {
    const row = button.closest(".result-actions");
    row.querySelectorAll(".rate-answer").forEach((item) => item.classList.remove("success"));
    button.classList.add("success");
    const retry = row.querySelector(".retry-different");
    retry.classList.toggle("hidden", button.dataset.rate !== "dislike");
  }

  if (button.classList.contains("retry-different")) {
    await runSuggestion("Попередній стиль не підійшов. Дай відповідь в іншому стилі: простіше, природніше і без зайвого тексту.");
  }
});

personForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!currentUser) {
    setFormStatus(personStatusText, "Спочатку увійди в акаунт.", "error");
    showView("profile");
    return;
  }
  const person = {
    id: uid(),
    name: document.querySelector("#personName").value.trim(),
    age: document.querySelector("#personAge").value.trim(),
    style: document.querySelector("#personStyle").value.trim(),
    likes: document.querySelector("#personLikes").value.trim(),
    dislikes: document.querySelector("#personDislikes").value.trim(),
    facts: document.querySelector("#personFacts").value.trim(),
    status: document.querySelector("#personStatus").value,
  };
  if (!person.name) {
    setFormStatus(personStatusText, "Додай хоча б ім'я.", "error");
    return;
  }
  savePeople([person, ...getPeople()]);
  fields.personProfile.value = person.id;
  personForm.reset();
  setFormStatus(personStatusText, "Профіль збережено.", "success");
});

peopleList.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const id = button.dataset.id;
  if (button.classList.contains("use-person")) {
    fields.personProfile.value = id;
    showView("chat");
  }
  if (button.classList.contains("delete-person")) {
    savePeople(getPeople().filter((person) => person.id !== id));
  }
});

favoritesList.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const id = button.dataset.id;
  const item = getFavorites().find((favorite) => favorite.id === id);
  if (button.classList.contains("copy-favorite") && item) await copyText(item.text, button);
  if (button.classList.contains("delete-favorite")) saveFavorites(getFavorites().filter((favorite) => favorite.id !== id));
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = document.querySelector("#registerName").value.trim();
  const email = document.querySelector("#registerEmail").value.trim();
  const password = document.querySelector("#registerPassword").value;

  if (!email || !password) {
    setFormStatus(registerStatus, "Введи email і пароль.", "error");
    return;
  }
  if (password.length < 6) {
    setFormStatus(registerStatus, "Пароль має бути мінімум 6 символів.", "error");
    return;
  }

  setFormStatus(registerStatus, "Створюю акаунт...", "info");
  setSubmitBusy(registerForm, true, "Створюю...");
  try {
    const data = await apiJson("/api/register", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    });
    clearAuthForms();
    updateAuthUi(data.user);
    addMessage("assistant", data.user.is_admin ? "Акаунт створено. Ти адмін." : "Акаунт створено.");
    await wait(300);
    showView("chat");
  } catch (error) {
    setFormStatus(registerStatus, error.message, "error");
  } finally {
    setSubmitBusy(registerForm, false);
  }
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = document.querySelector("#loginEmail").value.trim();
  const password = document.querySelector("#loginPassword").value;

  if (!email || !password) {
    setFormStatus(loginStatus, "Введи email і пароль.", "error");
    return;
  }

  setFormStatus(loginStatus, "Перевіряю акаунт...", "info");
  setSubmitBusy(loginForm, true, "Входжу...");
  try {
    const data = await apiJson("/api/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    clearAuthForms();
    updateAuthUi(data.user);
    addMessage("assistant", "Ти увійшов. Тепер історія, профілі й обране прив'язані саме до цього акаунта.");
    await wait(300);
    showView("chat");
  } catch (error) {
    setFormStatus(loginStatus, error.message, "error");
  } finally {
    setSubmitBusy(loginForm, false);
  }
});

logoutBtn.addEventListener("click", async () => {
  await apiJson("/api/logout", { method: "POST", body: "{}" });
  clearSessionUi();
  updateAuthUi(null);
  showView("chat");
});

changePasswordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await apiJson("/api/change-password", {
      method: "POST",
      body: JSON.stringify({ new_password: document.querySelector("#newPassword").value }),
    });
    document.querySelector("#newPassword").value = "";
    addMessage("assistant", "Пароль змінено.");
    showView("chat");
  } catch (error) {
    addMessage("assistant", error.message);
  }
});

adminPasswordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedAdminUser || selectedAdminUser.kind !== "site") return;
  try {
    await apiJson("/api/admin/reset-password", {
      method: "POST",
      body: JSON.stringify({
        user_id: selectedAdminUser.id,
        new_password: document.querySelector("#adminNewPassword").value,
      }),
    });
    document.querySelector("#adminNewPassword").value = "";
    adminHistory.textContent = "Пароль користувача змінено. Передай йому новий пароль приватно.";
  } catch (error) {
    adminHistory.textContent = error.message;
  }
});

loginBtn.addEventListener("click", () => showView("profile"));
refreshUsersBtn.addEventListener("click", loadAdminUsers);
toggleNewPasswordBtn.addEventListener("click", () => togglePassword("#newPassword", toggleNewPasswordBtn));
toggleAdminPasswordBtn.addEventListener("click", () => togglePassword("#adminNewPassword", toggleAdminPasswordBtn));

saveProfileBtn.addEventListener("click", () => {
  if (!currentUser) {
    showView("profile");
    return;
  }
  saveLocalSettings();
  addMessage("assistant", "Стиль збережено для цього акаунта.");
  showView("chat");
});

clearSessionUi();
refreshMe();
