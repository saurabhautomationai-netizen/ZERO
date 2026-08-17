/**
 * ZERO Web Command Center Client
 */

let allAgents = [];

document.addEventListener("DOMContentLoaded", () => {
  loadAgents();
});

async function loadAgents() {
  const rosterEl = document.getElementById("agent-roster");
  const countEl = document.getElementById("agent-count");

  try {
    const res = await fetch("/agents");
    if (!res.ok) throw new Error("Failed to load agents");
    const data = await res.json();

    const nativeList = data.native || [];
    const agencyList = data.agency || [];
    allAgents = [...nativeList, ...agencyList];

    if (countEl) {
      countEl.textContent = allAgents.length;
    }

    renderRoster(allAgents);
  } catch (err) {
    if (rosterEl) {
      rosterEl.innerHTML = `<div class="roster-loading">Failed to load agents list.</div>`;
    }
  }
}

function renderRoster(agents) {
  const rosterEl = document.getElementById("agent-roster");
  if (!rosterEl) return;

  if (agents.length === 0) {
    rosterEl.innerHTML = `<div class="roster-loading">No agents found.</div>`;
    return;
  }

  rosterEl.innerHTML = agents
    .slice(0, 30) // Render top 30 in sidebar for speed
    .map(
      (a) => `
      <div class="roster-item" onclick="selectAgent('${escapeHtml(a.name)}')">
        <span class="roster-name">${escapeHtml(a.name)}</span>
        <span class="roster-slug">${escapeHtml(a.slug)}</span>
      </div>
    `
    )
    .join("");
}

function filterAgents(query) {
  const q = query.toLowerCase().trim();
  if (!q) {
    renderRoster(allAgents);
    return;
  }

  const filtered = allAgents.filter(
    (a) =>
      a.name.toLowerCase().includes(q) ||
      a.slug.toLowerCase().includes(q) ||
      (a.description && a.description.toLowerCase().includes(q))
  );
  renderRoster(filtered);
}

function selectAgent(name) {
  const input = document.getElementById("task-input");
  if (input) {
    input.value = `Ask ${name}: `;
    input.focus();
  }
}

function toggleSidebar() {
  const sidebar = document.getElementById("sidebar");
  if (sidebar) {
    sidebar.classList.toggle("open");
  }
}

function autoResize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
}

function handleKeyDown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSubmit(e);
  }
}

function sendPrompt(text) {
  const input = document.getElementById("task-input");
  if (input) {
    input.value = text;
    handleSubmit(new Event("submit"));
  }
}

async function handleSubmit(e) {
  if (e) e.preventDefault();
  const input = document.getElementById("task-input");
  const task = input ? input.value.trim() : "";
  if (!task) return;

  // Hide welcome card once chat starts
  const welcomeCard = document.getElementById("welcome-card");
  if (welcomeCard) {
    welcomeCard.style.display = "none";
  }

  // Append user message
  appendUserMessage(task);
  input.value = "";
  input.style.height = "auto";

  // Append loading bot message
  const botMessageId = appendLoadingMessage();

  try {
    const res = await fetch("/task", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task }),
    });

    if (!res.ok) {
      throw new Error(`Server returned HTTP ${res.status}`);
    }

    const data = await res.json();
    updateBotMessage(botMessageId, data);
  } catch (err) {
    updateBotMessageError(botMessageId, err.message);
  }
}

function appendUserMessage(text) {
  const list = document.getElementById("messages-list");
  const msgEl = document.createElement("div");
  msgEl.className = "message-bubble message-user";
  msgEl.innerHTML = `<div class="message-body">${escapeHtml(text)}</div>`;
  list.appendChild(msgEl);
  scrollToBottom();
}

function appendLoadingMessage() {
  const list = document.getElementById("messages-list");
  const msgId = "msg-" + Date.now();
  const msgEl = document.createElement("div");
  msgEl.className = "message-bubble message-bot";
  msgEl.id = msgId;
  msgEl.innerHTML = `
    <div class="message-header">
      <span class="agent-badge">Orchestrating...</span>
    </div>
    <div class="message-body" style="color: var(--text-muted);">Routing task through ZERO Orchestrator...</div>
  `;
  list.appendChild(msgEl);
  scrollToBottom();
  return msgId;
}

function updateBotMessage(msgId, data) {
  const msgEl = document.getElementById(msgId);
  if (!msgEl) return;

  const selected = data.selected || {};
  const isNative = selected.source === "native";
  const badgeClass = isNative ? "badge-native" : "badge-agency";
  const agentName = selected.name || "Specialist Agent";
  const slug = selected.slug || "";

  let answerText = data.answer || "";
  if (data.needs_llm && !answerText && data.persona) {
    answerText = `[Specialist Persona Hand-off Ready]\n\n${data.persona.slice(0, 400)}...`;
  }

  msgEl.innerHTML = `
    <div class="message-header">
      <span class="agent-badge ${badgeClass}">${escapeHtml(agentName)}</span>
      <span style="font-size: 11px; font-family: var(--font-mono); color: var(--text-muted);">${escapeHtml(slug)}</span>
    </div>
    <div class="message-body">${formatMarkdown(answerText)}</div>
  `;
  scrollToBottom();
}

function updateBotMessageError(msgId, errorText) {
  const msgEl = document.getElementById(msgId);
  if (!msgEl) return;

  msgEl.innerHTML = `
    <div class="message-header">
      <span class="agent-badge" style="background: rgba(239, 68, 68, 0.1); color: #f87171; border-color: rgba(239, 68, 68, 0.25);">Error</span>
    </div>
    <div class="message-body" style="color: #f87171;">Failed to execute task: ${escapeHtml(errorText)}</div>
  `;
  scrollToBottom();
}

function clearChat() {
  const list = document.getElementById("messages-list");
  if (list) list.innerHTML = "";
  const welcomeCard = document.getElementById("welcome-card");
  if (welcomeCard) welcomeCard.style.display = "block";
}

function scrollToBottom() {
  const container = document.getElementById("chat-container");
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

function escapeHtml(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatMarkdown(text) {
  if (!text) return "";
  let esc = escapeHtml(text);

  // Bold
  esc = esc.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  // Headers
  esc = esc.replace(/^### (.*$)/gim, "<h3>$1</h3>");
  esc = esc.replace(/^## (.*$)/gim, "<h2>$1</h2>");
  esc = esc.replace(/^# (.*$)/gim, "<h1>$1</h1>");
  // Inline code
  esc = esc.replace(/`(.*?)`/g, "<code>$1</code>");

  return esc;
}
