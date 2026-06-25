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
const saveProfileBtn = document.querySelector("#saveProfileBtn");
const modeBadge = document.querySelector("#modeBadge");
let lastPlainAnswer = "";

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
  return text
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
  return text
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
  const { cleaned, html } = formatAnswer(text);
  if (role === "assistant") lastPlainAnswer = cleaned;
  article.innerHTML = `<span>${role === "user" ? "Ти" : "AI"}</span>${html}`;
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
      const response = await fetch("/api/suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Помилка запиту");
      return data;
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

document.querySelectorAll(".nav-btn").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
    button.classList.add("active");
    document.querySelector(`#view-${button.dataset.view}`).classList.add("active");
  });
});

document.querySelectorAll(".scenario-card").forEach((card) => {
  card.addEventListener("click", () => {
    fields.situation.value = card.dataset.situation;
    fields.goal.value = card.dataset.goal;
    document.querySelector('[data-view="chat"]').click();
    fields.context.focus();
  });
});

generateBtn.addEventListener("click", async () => {
  const payload = collectPayload();
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

loginBtn.addEventListener("click", () => {
  document.querySelector('[data-view="profile"]').click();
});

saveProfileBtn.addEventListener("click", () => {
  saveLocalSettings();
  addMessage("assistant", "Кабінет збережено в цьому браузері. Реальна реєстрація потребує бази даних, її в Telegram-боті ще не було.");
  document.querySelector('[data-view="chat"]').click();
});

loadLocalSettings();
