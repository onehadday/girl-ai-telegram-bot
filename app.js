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

const generateBtn = document.querySelector("#generateBtn");
const copyBtn = document.querySelector("#copyBtn");
const result = document.querySelector("#result");
const modeBadge = document.querySelector("#modeBadge");
let plainResult = result.textContent;

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

function renderResult(text) {
  plainResult = cleanMarkdown(text);
  const lines = plainResult.split("\n");
  const html = lines
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return "";
      }

      const heading = trimmed.match(/^(Найкращий варіант|Ще варіанти|Чому це працює|Що не варто писати|Попередження|Best message|Other options|Why it works|Avoid):?$/i);
      if (heading) {
        return `<h3>${escapeHtml(trimmed.replace(/:$/, ""))}</h3>`;
      }

      const variant = trimmed.match(/^(М'якше|М’якше|Сміливіше|З гумором|Softer|Bolder|Funny):\s*(.+)$/i);
      if (variant) {
        return `<p class="variant"><strong>${escapeHtml(variant[1])}:</strong> ${escapeHtml(variant[2])}</p>`;
      }

      const numbered = trimmed.match(/^\d+\.\s*(.+)$/);
      if (numbered) {
        return `<p>${escapeHtml(numbered[1])}</p>`;
      }

      return `<p>${escapeHtml(trimmed)}</p>`;
    })
    .join("");
  result.innerHTML = html || escapeHtml(plainResult);
}

generateBtn.addEventListener("click", async () => {
  const payload = collectPayload();
  if (!payload.context) {
    renderResult("Додай переписку або короткий опис ситуації. Без контексту порада буде занадто загальна.");
    return;
  }

  setBusy(true);
  renderResult("Підбираю нормальну відповідь без нав'язливості...");

  try {
    const response = await fetch("/api/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Помилка запиту");
    }
    renderResult(data.text);
    modeBadge.textContent = data.mode || "готовий";
  } catch (error) {
    renderResult(`Не вийшло отримати відповідь.\n\n${error.message}`);
    modeBadge.textContent = "помилка";
  } finally {
    generateBtn.disabled = false;
    generateBtn.textContent = "Підібрати відповідь";
  }
});

copyBtn.addEventListener("click", async () => {
  await navigator.clipboard.writeText(plainResult);
  copyBtn.textContent = "Скопійовано";
  setTimeout(() => {
    copyBtn.textContent = "Копіювати";
  }, 1200);
});
