const fields = {
  situation: document.querySelector("#situation"),
  tone: document.querySelector("#tone"),
  language: document.querySelector("#language"),
  goal: document.querySelector("#goal"),
  style: document.querySelector("#style"),
  context: document.querySelector("#context"),
};

const generateBtn = document.querySelector("#generateBtn");
const copyBtn = document.querySelector("#copyBtn");
const result = document.querySelector("#result");
const modeBadge = document.querySelector("#modeBadge");

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

generateBtn.addEventListener("click", async () => {
  const payload = collectPayload();
  if (!payload.context) {
    result.textContent = "Додай переписку або короткий опис ситуації. Без контексту порада буде занадто загальна.";
    return;
  }

  setBusy(true);
  result.textContent = "Підбираю нормальну відповідь без нав'язливості...";

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
    result.textContent = data.text;
    modeBadge.textContent = data.mode || "готовий";
  } catch (error) {
    result.textContent = `Не вийшло отримати відповідь.\n\n${error.message}`;
    modeBadge.textContent = "помилка";
  } finally {
    generateBtn.disabled = false;
    generateBtn.textContent = "Підібрати відповідь";
  }
});

copyBtn.addEventListener("click", async () => {
  await navigator.clipboard.writeText(result.textContent);
  copyBtn.textContent = "Скопійовано";
  setTimeout(() => {
    copyBtn.textContent = "Копіювати";
  }, 1200);
});
