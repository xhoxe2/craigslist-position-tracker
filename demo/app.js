const knowledgeBase = [
  {
    id: "notion-deploy-checklist",
    title: "Notion: WooCommerce deploy checklist",
    tags: ["деплой", "woocommerce", "кошик", "checkout", "release"],
    score: 0.92,
    answer:
      "Для WooCommerce деплою я брав checklist з Notion: maintenance window, backup DB, smoke-test checkout на staging, release, потім контрольний тест кошика на production. Саме цей тип повторюваних питань RAG-бот закривав без senior-а.",
    source: "Notion / Engineering / Release checklist",
  },
  {
    id: "notion-acf-schema",
    title: "Notion: ACF field map for project Z",
    tags: ["acf", "поля", "field", "schema", "project z", "проекту z"],
    score: 0.89,
    answer:
      "Схема ACF-полів лежала в Notion, але її постійно питали в Slack. У MVP бот знаходив потрібний розділ, повертав короткий список group/key/name і додавав link на оригінальний документ.",
    source: "Notion / Project Z / ACF schema",
  },
  {
    id: "drive-staging-access",
    title: "Drive: onboarding and staging access",
    tags: ["staging", "credentials", "доступ", "нового", "розробника", "onboarding"],
    score: 0.84,
    answer:
      "Для staging-доступів бот не показував секрети напряму. Він вказував, де знаходиться процедура отримання доступу, хто approve owner і який канал використати для запиту.",
    source: "Google Drive / Onboarding / Access flow",
  },
  {
    id: "slack-old-project",
    title: "Slack export: incomplete 2023 thread",
    tags: ["2023", "project x", "проектом x", "старі", "slack"],
    score: 0.41,
    answer:
      "У пілоті старі Slack-треди ще не були повністю інтегровані. Relevance gate мав чесно відповісти, що джерел недостатньо, замість того щоб вигадувати деталі.",
    source: "Slack / partial export / needs re-ingest",
  },
];

const appState = {
  scanRows: [],
  weeklyRows: [],
};

function byId(id) {
  return document.getElementById(id);
}

function normalize(text) {
  return text.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, " ");
}

function scoreEntry(question, entry) {
  const q = normalize(question);
  const matches = entry.tags.filter((tag) => q.includes(normalize(tag)));
  return Math.min(0.98, entry.score + matches.length * 0.035 - (matches.length ? 0 : 0.28));
}

function runRag() {
  const question = byId("rag-question").value.trim();
  const threshold = Number(byId("rag-threshold").value);
  const status = byId("rag-status");
  const answer = byId("rag-answer");
  const sources = byId("rag-sources");

  const ranked = knowledgeBase
    .map((entry) => ({ ...entry, relevance: scoreEntry(question, entry) }))
    .sort((a, b) => b.relevance - a.relevance)
    .slice(0, 3);

  const top = ranked[0];
  sources.innerHTML = ranked
    .map(
      (entry) => `
        <li>
          <strong>${entry.title}</strong>
          <small>${entry.source} · relevance ${(entry.relevance * 100).toFixed(0)}%</small>
        </li>
      `,
    )
    .join("");

  if (!question) {
    status.className = "status-pill warn";
    status.textContent = "Empty";
    answer.textContent = "Питання порожнє. Введіть запит до бази.";
    return;
  }

  if (top.relevance < threshold) {
    status.className = "status-pill bad";
    status.textContent = `Gate ${(top.relevance * 100).toFixed(0)}%`;
    answer.textContent =
      "Не вистачає релевантних джерел. У реальному MVP бот відповідав би чесно: 'не знаю, спитай senior-а в #dev-help' і записав би це як gap у базі знань.";
    return;
  }

  status.className = "status-pill ok";
  status.textContent = `Gate ${(top.relevance * 100).toFixed(0)}%`;
  answer.textContent = `${top.answer} Джерело: ${top.source}.`;
}

function parseListings(raw) {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const [idPart, titlePart] = line.split("|");
      const id = (idPart || "").trim() || `demo-${index + 1}`;
      const title = (titlePart || "tracked listing").trim();
      return { id, title };
    });
}

function stableNumber(seed) {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) % 9973;
  }
  return hash;
}

function simulatePosition({ city, keyword, id, title, index, maxPages, proxyEnabled }) {
  const totalSeen = maxPages * 120;
  if (!proxyEnabled) {
    return { position: null, page: null, totalSeen: 0, blocked: true };
  }

  const seed = stableNumber(`${city}:${keyword}:${id}:${title}`);
  const likelyMissing = title.toLowerCase().includes("missing") || seed % 11 === 0;
  if (likelyMissing) {
    return { position: null, page: null, totalSeen, blocked: false };
  }

  const position = 1 + ((seed + index * 17) % Math.max(12, Math.min(totalSeen, 96)));
  return {
    position,
    page: Math.ceil(position / 120),
    totalSeen,
    blocked: false,
  };
}

function runScan() {
  const city = byId("city").value;
  const keyword = byId("keyword").value.trim() || "sample query";
  const maxPages = Math.max(1, Math.min(5, Number(byId("max-pages").value) || 3));
  const proxyEnabled = byId("proxy-enabled").checked;
  const listings = parseListings(byId("listings").value);
  const tbody = byId("scan-rows");
  const status = byId("scan-status");

  appState.scanRows = listings.map((listing, index) => {
    const scan = simulatePosition({ city, keyword, index, maxPages, proxyEnabled, ...listing });
    return { city, keyword, ...listing, ...scan };
  });

  tbody.innerHTML = appState.scanRows
    .map(
      (row) => `
        <tr>
          <td>${row.city}</td>
          <td>${row.keyword}</td>
          <td><code>${row.id}</code><br /><small>${row.title}</small></td>
          <td>${row.position ?? "not found"}</td>
          <td>${row.page ?? ""}</td>
          <td>${row.totalSeen}</td>
        </tr>
      `,
    )
    .join("");

  const missing = appState.scanRows.filter((row) => row.position === null).length;
  const blocked = appState.scanRows.some((row) => row.blocked);
  status.className = `status-pill ${blocked ? "bad" : missing ? "warn" : "ok"}`;
  status.textContent = blocked ? "Blocked" : `${appState.scanRows.length - missing}/${appState.scanRows.length} visible`;
  byId("weekly-summary").textContent = "Scan complete. Generate the weekly report to see trend recommendations.";
  byId("weekly-rows").innerHTML = "";
}

function buildWeeklyRows() {
  if (!appState.scanRows.length) {
    runScan();
  }

  appState.weeklyRows = appState.scanRows.map((row, rowIndex) => {
    const positions = [];
    for (let day = 0; day < 7; day += 1) {
      if (row.position === null || (stableNumber(`${row.id}:${day}`) + rowIndex) % 13 === 0) {
        positions.push(null);
      } else {
        positions.push(Math.max(1, row.position + Math.floor(day / 3) + ((day + rowIndex) % 3) - 1));
      }
    }
    const visible = positions.filter((pos) => pos !== null);
    return {
      ...row,
      runs: 7,
      daysVisible: visible.length,
      daysMissing: 7 - visible.length,
      avg: visible.length ? visible.reduce((sum, pos) => sum + pos, 0) / visible.length : null,
      best: visible.length ? Math.min(...visible) : null,
      worst: visible.length ? Math.max(...visible) : null,
      delta: visible.length > 1 ? visible[visible.length - 1] - visible[0] : null,
    };
  });
}

function runWeeklyReport() {
  buildWeeklyRows();
  const weekly = byId("weekly-rows");
  const summary = byId("weekly-summary");
  const visibleRows = appState.weeklyRows.filter((row) => row.daysVisible > 0);
  const unstable = appState.weeklyRows.filter((row) => row.daysMissing > 0);
  const worst = visibleRows.sort((a, b) => (b.avg || 0) - (a.avg || 0))[0];

  weekly.innerHTML = appState.weeklyRows
    .map(
      (row) => `
        <div class="mini-row">
          <div>
            <strong>${row.id}</strong><br />
            <span>${row.daysVisible}/7 visible · missing ${row.daysMissing}</span>
          </div>
          <div>
            <strong>${row.avg ? row.avg.toFixed(1) : "n/a"}</strong><br />
            <span>avg</span>
          </div>
        </div>
      `,
    )
    .join("");

  if (!visibleRows.length) {
    summary.textContent =
      "Усі оголошення не знайдені. Перший крок менеджера: перевірити proxy/location і вручну підтвердити, чи Craigslist не повертає blocked/captcha сторінку.";
    return;
  }

  const parts = [
    `За тиждень видимими були ${visibleRows.length} з ${appState.weeklyRows.length} оголошень.`,
    unstable.length
      ? `${unstable.length} оголошення мали випадіння з видачі, їх варто перевірити першими.`
      : "Випадінь з видачі не було.",
  ];

  if (worst) {
    parts.push(
      `Найслабший рядок зараз ${worst.id}: avg position ${worst.avg.toFixed(1)}, worst ${worst.worst}. Рекомендація: оновити пост або перевірити конкурентні оголошення за тим самим keyword.`,
    );
  }

  summary.textContent = parts.join(" ");
}

function activateTab(tabId) {
  const caseTab = byId("tab-case");
  const trackerTab = byId("tab-tracker");
  const casePanel = byId("panel-case");
  const trackerPanel = byId("panel-tracker");
  const showCase = tabId === "case";

  caseTab.classList.toggle("is-active", showCase);
  trackerTab.classList.toggle("is-active", !showCase);
  caseTab.setAttribute("aria-selected", String(showCase));
  trackerTab.setAttribute("aria-selected", String(!showCase));
  casePanel.classList.toggle("is-active", showCase);
  trackerPanel.classList.toggle("is-active", !showCase);
  casePanel.hidden = !showCase;
  trackerPanel.hidden = showCase;
}

document.addEventListener("DOMContentLoaded", () => {
  byId("tab-case").addEventListener("click", () => activateTab("case"));
  byId("tab-tracker").addEventListener("click", () => activateTab("tracker"));
  byId("rag-run").addEventListener("click", runRag);
  byId("scan-run").addEventListener("click", runScan);
  byId("weekly-run").addEventListener("click", runWeeklyReport);

  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      byId("rag-question").value = button.dataset.question;
      runRag();
    });
  });

  runRag();
  runScan();
});
