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
const changePasswordForm = document.querySelector("#changePasswordForm");
const refreshUsersBtn = document.querySelector("#refreshUsersBtn");
const adminPasswordForm = document.querySelector("#adminPasswordForm");
const toggleNewPasswordBtn = document.querySelector("#toggleNewPasswordBtn");
const toggleAdminPasswordBtn = document.querySelector("#toggleAdminPasswordBtn");
const adminUsers = document.querySelector("#adminUsers");
const adminHistory = document.querySelector("#adminHistory");
const selectedUserTitle = document.querySelector("#selectedUserTitle");
const selectedUserHint = document.querySelector("#selectedUserHint");
let currentUser = null;
let selectedAdminUser = null;

function collectPayload() {
  return Object.fromEntries(
    Object.entries(fields).map(([key, input]) => [key, input.value.trim()])
  );
}

function setBusy(isBusy) {
  generateBtn.disabled = isBusy;
  generateBtn.textContent = isBusy ? "Думаю..." : "Підібрати відповідь";
  modeBadge.textContent = isBusy ? "працюю" : "готовий";
}

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

function formatAnswer(text) {
  const cleaned = cleanMarkdown(text);
  const html = cleaned
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return "";

      const heading = trimmed.match(/^(Найкращий варіант|Ще варіанти|Чому це працює|Що не варто писати|Попередження|Best message|Other options|Why it works|Avoid):?$/i);
      if (heading) return `<h3>${escapeHtml(trimmed.replace(/:$/, ""))}</h3>`;

      const variant = trimmed.match(/^(М'якше|М’якше|Сміливіше|З гумором|Softer|Bolder|Funny):\s*(.+)$/i);
      if (variant) return `<p class="variant"><strong>${escapeHtml(variant[1])}:</strong> ${escapeHtml(variant[2])}</p>`;

      const numbered = trimmed.match(/^\d+\.\s*(.+)$/);
      if (numbered) return `<p>${escapeHtml(numbered[1])}</p>`;

      return `<p>${escapeHtml(trimmed)}</p>`;
    })
    .join("");
  return { cleaned, html };
}

function addMessage(role, text) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const { html } = formatAnswer(text);
  article.innerHTML = `<span>${role === "user" ? "Ти" : "AI"}</span>${html}`;
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
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

function saveLocalSettings() {
  const data = {
    style: fields.style.value,
    phraseBank: fields.phraseBank.value,
    avoidPhrases: fields.avoidPhrases.value,
    communicationMode: fields.communicationMode.value,
    profileName: document.querySelector("#profileName").value,
    profileAbout: document.querySelector("#profileAbout").value,
  };
  localStorage.setItem("girlAiSettings", JSON.stringify(data));
}

function loadLocalSettings() {
  const raw = localStorage.getItem("girlAiSettings");
  if (!raw) return;
  const data = JSON.parse(raw);
  for (const key of ["style", "phraseBank", "avoidPhrases", "communicationMode"]) {
    if (data[key] && fields[key]) fields[key].value = data[key];
  }
  document.querySelector("#profileName").value = data.profileName || "";
  document.querySelector("#profileAbout").value = data.profileAbout || "";
}

function updateAuthUi(user) {
  currentUser = user;
  if (user) {
    authStatus.textContent = user.is_admin ? `${user.name} · адмін` : user.name;
    loginBtn.classList.add("hidden");
    logoutBtn.classList.remove("hidden");
  } else {
    authStatus.textContent = "гість";
    loginBtn.classList.remove("hidden");
    logoutBtn.classList.add("hidden");
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

async function loadAdminUsers() {
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
      .map((item) => `
        <article class="history-item">
          <div class="history-meta">
            <span>${escapeHtml(item.created_at || "")}</span>
            <span>${escapeHtml(item.source || "")}</span>
            <span>${escapeHtml(item.mode || "")}</span>
          </div>
          <h4>Що написали</h4>
          <p>${escapeHtml(item.prompt || "")}</p>
          <h4>Що відповів AI</h4>
          <p>${escapeHtml(cleanMarkdown(item.response || ""))}</p>
        </article>
      `)
      .join("");
  } catch (error) {
    adminHistory.textContent = error.message;
  }
}

document.querySelectorAll(".nav-btn").forEach((button) => {
  button.addEventListener("click", () => {
    showView(button.dataset.view);
    if (button.dataset.view === "admin") loadAdminUsers();
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

generateBtn.addEventListener("click", async () => {
  const payload = collectPayload();
  if (!currentUser) {
    addMessage("assistant", "Спочатку зареєструйся або увійди в Кабінеті. Без акаунта сайт не надсилає повідомлення.");
    showView("profile");
    return;
  }
  if (!payload.context) {
    addMessage("assistant", "Додай переписку або короткий опис ситуації. Без контексту порада буде занадто загальна.");
    return;
  }

  saveLocalSettings();
  addMessage("user", payload.context);
  setBusy(true);

  try {
    const data = await requestSuggestion(payload);
    addMessage("assistant", data.text);
    modeBadge.textContent = data.mode || "готовий";
  } catch (error) {
    addMessage("assistant", `Не вийшло отримати відповідь.\n\nСпробуй ще раз через 20-30 секунд. На безкоштовному Render сервер іноді засинає.\n\nТехнічно: ${error.message}`);
    modeBadge.textContent = "помилка";
  } finally {
    setBusy(false);
  }
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await apiJson("/api/register", {
      method: "POST",
      body: JSON.stringify({
        name: document.querySelector("#registerName").value,
        email: document.querySelector("#registerEmail").value,
        password: document.querySelector("#registerPassword").value,
      }),
    });
    updateAuthUi(data.user);
    addMessage("assistant", data.user.is_admin ? "Акаунт створено. Ти адмін, бо це перший акаунт." : "Акаунт створено.");
    showView("chat");
  } catch (error) {
    addMessage("assistant", error.message);
  }
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await apiJson("/api/login", {
      method: "POST",
      body: JSON.stringify({
        email: document.querySelector("#loginEmail").value,
        password: document.querySelector("#loginPassword").value,
      }),
    });
    updateAuthUi(data.user);
    addMessage("assistant", "Ти увійшов.");
    showView("chat");
  } catch (error) {
    addMessage("assistant", error.message);
  }
});

logoutBtn.addEventListener("click", async () => {
  await apiJson("/api/logout", { method: "POST", body: "{}" });
  updateAuthUi(null);
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
  saveLocalSettings();
  addMessage("assistant", "Стиль збережено в цьому браузері.");
  showView("chat");
});

loadLocalSettings();
refreshMe();

