// IP Sakti Sahayak — frontend logic.
// Talks only to the local FastAPI backend (same origin, so no CORS setup
// needed). Renders formulation categories and regime filters from the API
// rather than hardcoding them, so the sidebar always matches the backend's
// actual corpus metadata.

const state = {
  categories: [],
  regimeTypes: [],
  selectedCategoryId: null,
  selectedRegimeType: null,
  useLLM: false,
  consentLogging: true,
  micLang: "en-IN",
  backendReady: false,
};

const el = {
  statusDot: document.getElementById("status-dot"),
  statusText: document.getElementById("status-text"),
  setupBanner: document.getElementById("setup-banner"),
  transcript: document.getElementById("transcript"),
  composer: document.getElementById("composer"),
  questionInput: document.getElementById("question-input"),
  sendBtn: document.getElementById("send-btn"),
  categoryList: document.getElementById("category-list"),
  categoryDetail: document.getElementById("category-detail"),
  regimeSelect: document.getElementById("regime-select"),
  llmToggle: document.getElementById("llm-toggle"),
  consentToggle: document.getElementById("consent-toggle"),
  micBtn: document.getElementById("mic-btn"),
  micLangBtn: document.getElementById("mic-lang-btn"),
};

const tplUser = document.getElementById("tpl-user-message");
const tplAssistant = document.getElementById("tpl-assistant-message");

init();

async function init() {
  bindComposer();
  bindExampleChips();
  el.llmToggle.addEventListener("change", () => {
    state.useLLM = el.llmToggle.checked;
  });
  el.consentToggle.addEventListener("change", () => {
    state.consentLogging = el.consentToggle.checked;
  });
  setupVoiceInput();

  await Promise.all([loadHealth(), loadCategories(), loadRegimeTypes()]);
}

// --------------------------------------------------------------------------
// Startup: backend health + sidebar data
// --------------------------------------------------------------------------

async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    state.backendReady = !!data.ready;
    if (data.ready) {
      setStatus("ready", `Connected · ${data.chunk_count} chunks · ${data.model}`);
      el.setupBanner.hidden = true;
    } else {
      setStatus("error", "Vector database not ready.");
      el.setupBanner.hidden = false;
    }
  } catch (err) {
    setStatus("error", "Could not reach the backend. Is uvicorn running?");
    el.setupBanner.hidden = false;
  }
}

function setStatus(kind, text) {
  el.statusDot.className = `status-dot status-dot--${kind}`;
  el.statusText.textContent = text;
}

async function loadCategories() {
  try {
    const res = await fetch("/api/formulation-categories");
    state.categories = await res.json();
    renderCategoryList();
  } catch (err) {
    // Non-fatal: the app still works without the classifier.
    console.warn("Could not load formulation categories", err);
  }
}

async function loadRegimeTypes() {
  try {
    const res = await fetch("/api/regime-types");
    state.regimeTypes = await res.json();
    renderRegimeSelect();
  } catch (err) {
    console.warn("Could not load regime types", err);
  }
}

// Small inline line-art icons per formulation category, matching the brand
// motif style. Falls back to a generic leaf icon for any unrecognised id.
const CATEGORY_ICONS = {
  classical: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M6 4h9l3 3v13H6z"/><path d="M9 10h6M9 14h6M9 18h3"/></svg>',
  patent_proprietary: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="12" cy="9" r="5"/><path d="M9 13l-2 7 5-3 5 3-2-7"/></svg>',
  new_drug: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3"/><path d="M8 15h8"/></svg>',
  phytopharmaceutical: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M12 3s6 6 6 11a6 6 0 0 1-12 0c0-5 6-11 6-11z"/></svg>',
  ayurveda_aahar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M4 12a8 4 0 0 0 16 0"/><path d="M4 12a8 4 0 0 1 16 0"/><path d="M12 4v3"/></svg>',
  cosmetic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M12 3l7 4v5c0 5-3 8-7 9-4-1-7-4-7-9V7z"/></svg>',
  _default: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M12 3s6 6 6 11a6 6 0 0 1-12 0c0-5 6-11 6-11z"/></svg>',
};

function renderCategoryList() {
  el.categoryList.innerHTML = "";
  state.categories.forEach((cat) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "category-card";
    btn.setAttribute("role", "option");
    btn.setAttribute("aria-selected", "false");
    btn.innerHTML = `${CATEGORY_ICONS[cat.id] || CATEGORY_ICONS._default}<span>${escapeHTML(cat.label)}</span>`;
    btn.addEventListener("click", () => selectCategory(cat.id));
    el.categoryList.appendChild(btn);
  });
}

function selectCategory(id) {
  state.selectedCategoryId = state.selectedCategoryId === id ? null : id;
  [...el.categoryList.children].forEach((btn, i) => {
    const isSelected = state.categories[i].id === state.selectedCategoryId;
    btn.setAttribute("aria-selected", String(isSelected));
  });

  const cat = state.categories.find((c) => c.id === state.selectedCategoryId);
  if (!cat) {
    el.categoryDetail.hidden = true;
    return;
  }
  el.categoryDetail.hidden = false;
  el.categoryDetail.innerHTML = `
    <p><span class="cd-label">Requires:</span> ${escapeHTML(cat.hint)}</p>
    <p><span class="cd-label">IP posture:</span> ${escapeHTML(cat.posture)}</p>
  `;
}

function renderRegimeSelect() {
  el.regimeSelect.innerHTML = "";
  state.regimeTypes.forEach((rt) => {
    const opt = document.createElement("option");
    opt.value = rt.id ?? "";
    opt.textContent = rt.label;
    el.regimeSelect.appendChild(opt);
  });
  el.regimeSelect.addEventListener("change", () => {
    state.selectedRegimeType = el.regimeSelect.value || null;
  });
}

// --------------------------------------------------------------------------
// Chat
// --------------------------------------------------------------------------

function bindExampleChips() {
  document.querySelectorAll(".example-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      el.questionInput.value = chip.dataset.example;
      el.questionInput.focus();
    });
  });
}

function bindComposer() {
  el.composer.addEventListener("submit", (e) => {
    e.preventDefault();
    submitQuestion();
  });
  el.questionInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitQuestion();
    }
  });
  el.questionInput.addEventListener("input", () => {
    el.questionInput.style.height = "auto";
    el.questionInput.style.height = `${Math.min(el.questionInput.scrollHeight, 140)}px`;
  });
}

// --------------------------------------------------------------------------
// Voice input -- browser-native Web Speech API only (no backend key, no
// server round-trip). Feature-detected: the mic buttons stay hidden on
// browsers without support (e.g. Firefox desktop) instead of showing a
// button that would just fail. This is the realistic slice of "voice
// experience" available without a paid speech-to-text integration.
// --------------------------------------------------------------------------
function setupVoiceInput() {
  const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognitionCtor) return; // no support: leave both buttons hidden

  const recognition = new SpeechRecognitionCtor();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = state.micLang;

  let listening = false;

  el.micBtn.hidden = false;
  el.micLangBtn.hidden = false;
  el.micLangBtn.textContent = "EN";

  el.micLangBtn.addEventListener("click", () => {
    state.micLang = state.micLang === "en-IN" ? "hi-IN" : "en-IN";
    recognition.lang = state.micLang;
    el.micLangBtn.textContent = state.micLang === "hi-IN" ? "हिं" : "EN";
  });

  el.micBtn.addEventListener("click", () => {
    if (listening) {
      recognition.stop();
      return;
    }
    try {
      recognition.lang = state.micLang;
      recognition.start();
    } catch (err) {
      console.warn("Could not start voice input", err);
    }
  });

  recognition.addEventListener("start", () => {
    listening = true;
    el.micBtn.classList.add("mic-btn--active");
  });
  recognition.addEventListener("end", () => {
    listening = false;
    el.micBtn.classList.remove("mic-btn--active");
  });
  recognition.addEventListener("error", () => {
    listening = false;
    el.micBtn.classList.remove("mic-btn--active");
  });
  recognition.addEventListener("result", (event) => {
    const transcript = event.results?.[0]?.[0]?.transcript;
    if (!transcript) return;
    const existing = el.questionInput.value.trim();
    el.questionInput.value = existing ? `${existing} ${transcript}` : transcript;
    el.questionInput.dispatchEvent(new Event("input"));
    el.questionInput.focus();
  });
}

async function submitQuestion() {
  const question = el.questionInput.value.trim();
  if (!question || el.sendBtn.disabled) return;

  clearEmptyState();
  appendUserMessage(question);
  el.questionInput.value = "";
  el.questionInput.style.height = "auto";

  const typingNode = appendTypingIndicator();
  setComposerBusy(true);

  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        regime_type: state.selectedRegimeType,
        formulation_category_id: state.selectedCategoryId,
        top_k: 6,
        use_llm: state.useLLM,
        log_consent: state.consentLogging,
      }),
    });
    const data = await res.json();
    typingNode.remove();

    if (!data.ok) {
      appendSystemError(data.error || "The backend could not answer that.");
      return;
    }
    appendAssistantMessage(data, question);
  } catch (err) {
    typingNode.remove();
    appendSystemError("Could not reach the backend. Is uvicorn still running?");
  } finally {
    setComposerBusy(false);
  }
}

function setComposerBusy(busy) {
  el.sendBtn.disabled = busy;
  el.sendBtn.textContent = busy ? "Searching…" : "Ask";
}

function clearEmptyState() {
  const empty = el.transcript.querySelector(".empty-state");
  if (empty) empty.remove();
}

function appendUserMessage(text) {
  const node = tplUser.content.cloneNode(true);
  node.querySelector(".msg-bubble").textContent = text;
  el.transcript.appendChild(node);
  scrollToBottom();
}

function appendTypingIndicator() {
  const wrap = document.createElement("div");
  wrap.className = "msg msg--assistant";
  wrap.innerHTML = `<div class="typing"><span></span><span></span><span></span></div>`;
  el.transcript.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function appendSystemError(text) {
  const wrap = document.createElement("div");
  wrap.className = "msg msg--assistant";
  wrap.innerHTML = `<div class="msg-body">${escapeHTML(text)}</div>`;
  el.transcript.appendChild(wrap);
  scrollToBottom();
}

function appendAssistantMessage(data, question) {
  const node = tplAssistant.content.cloneNode(true);
  const root = node.querySelector(".msg--assistant");

  const pill = node.querySelector(".confidence-pill");
  const confidenceLabel = { high: "High confidence", medium: "Medium confidence", low: "Low confidence", none: "No match", general: "General guidance" }[data.confidence] || data.confidence;
  pill.textContent = data.best_distance != null ? `${confidenceLabel} · distance ${data.best_distance.toFixed(3)}` : confidenceLabel;
  pill.classList.add(`confidence-pill--${data.confidence}`);

  if (data.category) {
    const tag = node.querySelector(".category-tag");
    tag.hidden = false;
    tag.textContent = data.category.label;
  }

  node.querySelector(".msg-body").innerHTML = renderAnswerMarkdown(data.answer);

  if (data.abs_tkdl_flag) {
    node.querySelector(".abs-alert").hidden = false;
  }

  if (data.escalate) {
    const row = node.querySelector(".escalate-row");
    row.hidden = false;
    const link = row.querySelector(".escalate-link");
    const isHindi = /[\u0900-\u097f]/.test(question || "");
    const subjectText = isHindi ? "IP Sakti Sahayak — समीक्षा अनुरोध" : "IP Sakti Sahayak — review request";
    const bodyText = isHindi
      ? `प्रश्न: ${question || "(बातचीत देखें)"}\n\nमानव IP-सुविधाकर्ता समीक्षा का अनुरोध — इस प्रश्न के लिए स्वचालित विश्वास स्तर कम था।`
      : `Question: ${question || "(see conversation)"}\n\nRequesting human IP-facilitator review — the automated confidence was low for this query.`;
    link.textContent = isHindi ? "मानव IP सुविधाकर्ता से समीक्षा का अनुरोध करें" : "Request human IP facilitator review";
    link.href = `mailto:facilitator@example.org?subject=${encodeURIComponent(subjectText)}&body=${encodeURIComponent(bodyText)}`;
  }

  const results = data.results || [];
  const sourcesBlock = node.querySelector(".sources");
  // Conversational replies have no retrieved legal source. Hide the empty
  // accordion instead of suggesting that a greeting has citations behind it.
  sourcesBlock.hidden = results.length === 0;
  node.querySelector(".sources-count").textContent = `(${results.length})`;
  const list = node.querySelector(".sources-list");
  const EXCERPT_PREVIEW_LEN = 220;
  results.forEach((item) => {
    const li = document.createElement("li");
    li.className = "source-item";
    const meta = item.metadata || {};
    const excerpt = (item.text || "").replace(/\s+/g, " ").trim();
    const section = meta.section_or_clause || "";
    const sectionLabel = section && !section.includes(";") ? section : "Retrieved passage";

    li.innerHTML = `
      <div class="source-head">
        <span class="source-act">${escapeHTML(meta.act_name || "Unknown Act")}</span>
        <span class="source-distance">distance ${item.distance != null ? item.distance.toFixed(3) : "n/a"}</span>
      </div>
      <div class="source-sub">${escapeHTML(sectionLabel)} · p.${escapeHTML(String(meta.page_number ?? "n/a"))} · ${escapeHTML(meta.regime_type || "unclassified")}</div>
      <blockquote class="source-excerpt"></blockquote>
    `;

    const excerptEl = li.querySelector(".source-excerpt");
    if (excerpt.length > EXCERPT_PREVIEW_LEN) {
      const preview = excerpt.slice(0, EXCERPT_PREVIEW_LEN).trim();
      const previewSpan = document.createElement("span");
      previewSpan.className = "source-excerpt-text";
      previewSpan.textContent = `${preview}…`;
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "source-toggle";
      toggle.textContent = "Show full excerpt";
      let expanded = false;
      toggle.addEventListener("click", () => {
        expanded = !expanded;
        previewSpan.textContent = expanded ? excerpt : `${preview}…`;
        toggle.textContent = expanded ? "Show less" : "Show full excerpt";
      });
      excerptEl.appendChild(previewSpan);
      excerptEl.appendChild(document.createTextNode(" "));
      excerptEl.appendChild(toggle);
    } else {
      excerptEl.textContent = excerpt;
    }

    list.appendChild(li);
  });

  const related = data.related_sources || [];
  const relatedBlock = node.querySelector(".related-sources");
  if (related.length) {
    relatedBlock.hidden = false;
    node.querySelector(".related-count").textContent = `(${related.length})`;
    const relatedList = node.querySelector(".related-list");
    related.forEach((item) => {
      const li = document.createElement("li");
      li.className = "source-item";
      const meta = item.metadata || {};
      const excerpt = (item.text || "").replace(/\s+/g, " ").trim();
      const preview = excerpt.length > 160 ? `${excerpt.slice(0, 160).trim()}…` : excerpt;
      const section = meta.section_or_clause || "";
      const sectionLabel = section && !section.includes(";") ? section : "Retrieved passage";
      li.innerHTML = `
        <div class="source-head">
          <span class="source-act">${escapeHTML(meta.act_name || "Unknown Act")}</span>
        </div>
        <div class="source-sub">${escapeHTML(sectionLabel)} · p.${escapeHTML(String(meta.page_number ?? "n/a"))}</div>
        <blockquote class="source-excerpt">${escapeHTML(preview)}</blockquote>
      `;
      relatedList.appendChild(li);
    });
  }

  el.transcript.appendChild(node);
  scrollToBottom();
}

function scrollToBottom() {
  el.transcript.scrollTop = el.transcript.scrollHeight;
}

function escapeHTML(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

// --------------------------------------------------------------------------
// Tiny Markdown-lite renderer for assistant answers.
// Backend returns **bold** labels, *italic* caveats, "- " bullet lines and
// blank-line-separated paragraphs -- this converts just that small subset to
// HTML so the key claim / conditions / sources are visually distinct instead
// of one long run-on paragraph. Deliberately not a full Markdown parser:
// only handles the subset rag_engine.py actually emits.
function renderAnswerMarkdown(raw) {
  const text = raw ?? "";
  const blocks = text.split(/\n\n+/).map((b) => b.trim()).filter(Boolean);

  return blocks
    .map((block) => {
      const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
      const isList = lines.length > 0 && lines.every((l) => l.startsWith("- "));
      if (isList) {
        const items = lines.map((l) => `<li>${renderInlineMarkdown(l.slice(2))}</li>`).join("");
        return `<ul class="msg-list">${items}</ul>`;
      }
      return `<p>${renderInlineMarkdown(lines.join(" "))}</p>`;
    })
    .join("");
}

function renderInlineMarkdown(str) {
  // Escape first so raw text can never inject HTML, then reintroduce only
  // the **bold** / *italic* markers as real tags.
  let out = escapeHTML(str);
  out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*(.+?)\*/g, "<em>$1</em>");
  return out;
}
