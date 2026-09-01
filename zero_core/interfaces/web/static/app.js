/* ==========================================================================
   ZERO — JARVIS CYBERNETIC COCKPIT & PATROL JAVASCRIPT ENGINE
   ========================================================================== */

let isAudioEnabled = true;
let audioCtx = null;
let allAgents = [];

// Initialize Web Audio API for Futuristic HUD Sound Effects
function initAudio() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
}

function playSound(type) {
  if (!isAudioEnabled) return;
  try {
    initAudio();
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);

    const now = audioCtx.currentTime;

    if (type === 'blip') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(800, now);
      osc.frequency.exponentialRampToValueAtTime(1400, now + 0.05);
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
      osc.start(now);
      osc.stop(now + 0.05);
    } else if (type === 'approve') {
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(520, now);
      osc.frequency.setValueAtTime(880, now + 0.08);
      osc.frequency.setValueAtTime(1320, now + 0.16);
      gain.gain.setValueAtTime(0.12, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
      osc.start(now);
      osc.stop(now + 0.25);
    } else if (type === 'alert') {
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(400, now);
      osc.frequency.setValueAtTime(300, now + 0.1);
      gain.gain.setValueAtTime(0.1, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
      osc.start(now);
      osc.stop(now + 0.2);
    }
  } catch (e) {
    // Audio context not allowed without interaction
  }
}

function toggleSound() {
  isAudioEnabled = !isAudioEnabled;
  const btn = document.getElementById('btn-sound');
  if (btn) {
    btn.textContent = isAudioEnabled ? '🔊 SFX ON' : '🔇 SFX OFF';
    btn.style.color = isAudioEnabled ? 'var(--cyan-core)' : 'var(--text-dim)';
  }
  if (isAudioEnabled) playSound('blip');
}

// Sidebar Toggle
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar) {
    sidebar.classList.toggle('collapsed');
  }
  playSound('blip');
}

// Auto resize input textarea
function autoResize(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';
}

function handleKeyDown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    handleSubmit(event);
  }
}

function sendPrompt(promptText) {
  const input = document.getElementById('task-input');
  if (input) {
    input.value = promptText;
    autoResize(input);
    handleSubmit(new Event('submit'));
  }
  playSound('blip');
}

// Render Chat Message
function appendMessage(role, agentName, content) {
  const list = document.getElementById('messages-list');
  const welcome = document.getElementById('welcome-card');
  if (welcome) welcome.style.display = 'none';

  const card = document.createElement('div');
  card.className = `message-card ${role}`;

  const header = document.createElement('div');
  header.className = 'message-header';

  const title = document.createElement('span');
  title.className = role === 'user' ? 'user-badge' : 'agent-badge';
  title.textContent = role === 'user' ? 'OPERATOR' : (agentName || 'ZERO ORCHESTRATOR');

  const time = document.createElement('span');
  time.className = 'message-time';
  time.textContent = new Date().toLocaleTimeString();

  header.appendChild(title);
  header.appendChild(time);

  const body = document.createElement('div');
  body.className = 'message-body';

  // Format code blocks or markdown simply
  if (content.includes('```')) {
    body.innerHTML = content
      .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
      .replace(/\n/g, '<br>');
  } else {
    body.innerHTML = content.replace(/\n/g, '<br>');
  }

  card.appendChild(header);
  card.appendChild(body);
  list.appendChild(card);

  // Scroll to bottom
  const container = document.getElementById('chat-container');
  if (container) container.scrollTop = container.scrollHeight;
}

// Dispatch Task to Backend
async function handleSubmit(event) {
  if (event) event.preventDefault();
  const input = document.getElementById('task-input');
  const task = input.value.trim();
  if (!task) return;

  playSound('blip');
  appendMessage('user', null, task);
  input.value = '';
  autoResize(input);

  const radar = document.getElementById('radar-status');
  if (radar) radar.textContent = 'ROUTING TASK...';

  try {
    const res = await fetch('/api/task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task }),
    });

    let data;
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      data = await res.json();
    } else {
      const rawText = await res.text();
      data = {
        selected: { name: 'ZERO Core' },
        answer: res.ok ? rawText : `⚠️ Server Error (${res.status}): ${rawText || res.statusText}`,
        status: res.ok ? 'SUCCESS' : 'ERROR',
      };
    }

    const agentName = data.selected ? data.selected.name : 'ZERO Core';
    const answer = data.answer || JSON.stringify(data, null, 2);

    appendMessage('agent', agentName, answer);
    if (radar) radar.textContent = `DISPATCHED: ${agentName.toUpperCase()}`;
    playSound(res.ok ? 'approve' : 'alert');
  } catch (err) {
    appendMessage('agent', 'ERROR', `Failed to execute task: ${err.message}`);
    if (radar) radar.textContent = 'TASK ROUTING ERROR';
    playSound('alert');
  }
}

function clearChat() {
  const list = document.getElementById('messages-list');
  const welcome = document.getElementById('welcome-card');
  if (list) list.innerHTML = '';
  if (welcome) welcome.style.display = 'block';
  playSound('blip');
}

// Specialist Agent Roster Fetching & Filtering
async function loadAgents() {
  try {
    const res = await fetch('/api/agents');
    const data = await res.json();
    const native = data.native || [];
    const agency = data.agency || [];
    allAgents = [...native, ...agency];

    const badge = document.getElementById('agent-count');
    if (badge) badge.textContent = allAgents.length;

    renderRoster(allAgents);

    // Dynamically wire all 284 specialists into the Altari Neural SkillTree
    wireAgentsToNeuralSkillTree(allAgents);
  } catch (e) {
    const roster = document.getElementById('agent-roster');
    if (roster) roster.innerHTML = '<div class="roster-loading">Failed to load agents</div>';
  }
}

function renderRoster(agents) {
  const roster = document.getElementById('agent-roster');
  if (!roster) return;
  roster.innerHTML = '';

  agents.forEach(agent => {
    const div = document.createElement('div');
    div.className = 'roster-item';
    div.title = agent.description || agent.name;
    div.innerHTML = `
      <span class="roster-agent-name">${agent.name}</span>
      <span class="roster-div-badge">${agent.division || 'specialist'}</span>
    `;
    div.onclick = () => {
      sendPrompt(`@${agent.name}: `);
    };
    roster.appendChild(div);
  });
}

function filterAgents(query) {
  const q = query.toLowerCase().trim();
  if (!q) {
    renderRoster(allAgents);
    return;
  }
  const filtered = allAgents.filter(a =>
    a.name.toLowerCase().includes(q) ||
    a.division.toLowerCase().includes(q) ||
    (a.description && a.description.toLowerCase().includes(q))
  );
  renderRoster(filtered);
}

// ==========================================================================
// AUTONOMOUS PROJECT PATROL & HITL APPROVAL POLLER
// ==========================================================================

async function fetchPatrolStatus() {
  try {
    const res = await fetch('/api/patrol/status');
    const data = await res.json();

    const pillText = document.getElementById('patrol-pill-text');
    const statusVal = document.getElementById('patrol-status-val');
    const countVal = document.getElementById('patrol-projects-count');
    const lastRunVal = document.getElementById('patrol-last-run');
    const tagList = document.getElementById('projects-tag-list');

    if (pillText) pillText.textContent = `PATROL: ${data.is_running ? 'SCANNING...' : 'ACTIVE'}`;
    if (statusVal) statusVal.textContent = data.is_running ? 'SCANNING' : 'ONLINE';
    if (countVal) countVal.textContent = `${data.projects_count} ACTIVE`;
    if (lastRunVal && data.last_run) {
      lastRunVal.textContent = new Date(data.last_run).toLocaleTimeString();
    }

    if (tagList && data.projects_scanned) {
      tagList.innerHTML = data.projects_scanned
        .map(p => `<span class="proj-tag">${p}</span>`)
        .join('');
    }
  } catch (e) {
    // Backend offline or polling error
  }
}

async function triggerPatrol() {
  playSound('blip');
  const pillText = document.getElementById('patrol-pill-text');
  if (pillText) pillText.textContent = 'PATROL: SCANNING...';

  try {
    const res = await fetch('/api/patrol/trigger', { method: 'POST' });
    const data = await res.json();
    playSound('approve');
    fetchPatrolStatus();
    fetchPendingApprovals();
  } catch (e) {
    playSound('alert');
  }
}

async function fetchPendingApprovals() {
  try {
    const res = await fetch('/api/approvals/pending');
    const data = await res.json();
    const list = document.getElementById('approval-queue-list');
    const badge = document.getElementById('pending-count');
    const hitlPill = document.getElementById('hitl-pill-text');

    const count = data.count || 0;
    if (badge) badge.textContent = count;
    if (hitlPill) hitlPill.textContent = `HITL: ${count} PENDING`;

    if (!list) return;

    if (count === 0) {
      list.innerHTML = '<div class="empty-state">No pending approval requests. Systems operating safely.</div>';
      return;
    }

    list.innerHTML = '';
    data.approvals.forEach(appr => {
      const p = appr.parameters || {};
      const card = document.createElement('div');
      card.className = 'approval-card';
      card.innerHTML = `
        <div class="approval-card-title">${p.title || appr.action_type}</div>
        <div class="approval-card-desc">${p.description || appr.target}</div>
        <div style="font-family:var(--font-mono); font-size:0.65rem; color:var(--cyan-core); margin-bottom:6px;">
          Agent: ${p.agent || 'Security Auditor'} • Project: ${p.project_name || 'System'}
        </div>
        <div class="approval-actions">
          <button class="btn-approve" onclick="decideApproval('${appr.request_id}', 'approve')">✓ APPROVE & APPLY</button>
          <button class="btn-reject" onclick="decideApproval('${appr.request_id}', 'reject')">✕ REJECT</button>
        </div>
      `;
      list.appendChild(card);
    });
  } catch (e) {
    // Polling error
  }
}

async function decideApproval(requestId, decision) {
  playSound('blip');
  try {
    const res = await fetch(`/api/approvals/${requestId}/decide`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, approver: 'user' }),
    });
    const data = await res.json();
    playSound(decision === 'approve' ? 'approve' : 'alert');
    fetchPendingApprovals();
    fetchPatrolStatus();
  } catch (e) {
    alert('Failed to execute decision: ' + e.message);
  }
}

async function decideAllApprovals(decision) {
  if (!confirm(`Are you sure you want to ${decision.toUpperCase()} all pending proposals?`)) return;
  playSound('blip');
  try {
    const res = await fetch('/api/approvals/bulk-decide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, approver: 'user' }),
    });
    const data = await res.json();
    playSound(decision === 'approve' ? 'approve' : 'alert');
    fetchPendingApprovals();
    fetchPatrolStatus();
  } catch (e) {
    alert('Failed to execute bulk decision: ' + e.message);
  }
}


// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  loadAgents();
  fetchPatrolStatus();
  fetchPendingApprovals();

  // Periodic polling every 8 seconds
  setInterval(() => {
    fetchPatrolStatus();
    fetchPendingApprovals();
  }, 8000);
});

// ==========================================================================
// ALTARI-GRADE NEURAL SKILL TREE, 3D DASHBOARDS & ACTIONABLE DOSSIER
// ==========================================================================

let currentNeuralTab = 'map';
let neuralCanvasAnimId = null;
let currentDossierSkill = null;
let coverflowIndex = 0;
let isDraggingCoverflow = false;
let startX = 0;

// Central Brain Constellation Taxonomy
const NEURAL_ORG_DATA = [
  {
    id: 'marketing',
    name: 'MARKETING',
    deptTitle: 'MARKETING',
    deptSub: 'CONTENT · BRAND · DISTRIBUTION',
    angle: Math.PI * 1.25,
    radius: 260,
    color: '#c084fc',
    icon: '📢',
    jobs: [
      {
        id: 'ad_copy',
        name: 'Paid Ad Copywriter',
        dept: 'Marketing · Copywriting',
        desc: 'Generates high-converting hook angles, pain-point frameworks, and primary text variations for Meta, Google, and LinkedIn ads.',
        icon: '✍️',
        tags: ['meta-ads', 'copywriting', 'hook-generator', 'angle-tester'],
        tools: ['Meta Ads API', 'OpenAI', 'Gemini'],
        ladder: ['Drafting ad copy manually', 'Prompting generic ChatGPT for captions', 'Automated creative matrix running against ROAS benchmarks'],
        actions: [
          { label: '✍️ Write Ad Copy', prompt: '@Marketing Agent: Generate 3 high-converting ad copy angles with scroll-stopping hooks for our B2B SaaS offer' },
          { label: '🎨 Build Instagram Carousel', prompt: '@Marketing Agent: Create a 5-slide educational Instagram carousel outline with visual prompts' },
          { label: '📬 Generate Email Drip', prompt: '@Marketing Agent: Write a 3-part nurture email sequence addressing objection handling and social proof' }
        ]
      },
      {
        id: 'seo_cluster',
        name: 'SEO Topic Clusters',
        dept: 'Marketing · Organic Growth',
        desc: 'Identifies high-intent topical search clusters, low-competition keywords, and internal linking strategies to capture search traffic.',
        icon: '🔍',
        tags: ['seo', 'keyword-research', 'topic-clusters', 'content-strategy'],
        tools: ['Semrush', 'Ahrefs API', 'Search Console'],
        ladder: ['Manual spreadsheet keyword research', 'AI blog post writing', 'Autonomous cluster builder publishing directly to CMS'],
        actions: [
          { label: '🔍 Find Keyword Clusters', prompt: '@Marketing Agent: Generate a topical authority cluster around AI recruitment software' },
          { label: '📝 Draft Longform Article', prompt: '@Marketing Agent: Outline a 2,000-word authoritative guide on reducing time-to-hire with AI' }
        ]
      }
    ]
  },
  {
    id: 'sales',
    name: 'SALES',
    deptTitle: 'SALES',
    deptSub: 'TARGETING · OUTREACH · PROSPECTING',
    angle: Math.PI * 0.5,
    radius: 270,
    color: '#fbbf24',
    icon: '🎯',
    jobs: [
      {
        id: 'social_mining',
        name: 'Social Mining & Prospecting',
        dept: 'Sales · Lead Sourcing · 4 Jobs',
        desc: 'Harvest engaged audiences — post commenters, group members, and follower lists across LinkedIn, X, and GitHub.',
        icon: '👥',
        tags: ['comment-harvester', 'engagement-miner', 'profile-collector'],
        tools: ['Apollo', 'HeyReach', 'LinkedIn API'],
        ladder: ['Screenshotting commenters manually', 'Pointing an agent at a post to harvest & draft DMs', 'Watched keywords feed a standing warm-prospect pool continuously'],
        actions: [
          { label: '🎯 Harvest Leads Now', prompt: '@Talent Lead Gen Agent: Source 10 high-intent leads who commented on recent AI automation posts' },
          { label: '✉️ Draft Personalized DM', prompt: '@Sales Agent: Write a hyper-personalized, non-spammy cold message for an engineering VP' },
          { label: '🔍 Run ICP Qualification', prompt: '@Sales Agent: Qualify our lead list against company size >20 and recent hiring activity' }
        ]
      },
      {
        id: 'list_building',
        name: 'List Building',
        dept: 'Sales · Targeting',
        desc: 'Builds targeted lead lists from databases, directories, and search engines with verified contact records.',
        icon: '📑',
        tags: ['list-builder', 'contact-scraper', 'b2b-leads'],
        tools: ['Apollo', 'ZoomInfo', 'Clearbit'],
        ladder: ['Manual directory searches', 'CSV exports and cleanups', 'Continuous autonomous pipeline feeding enriched accounts into CRM'],
        actions: [
          { label: '📑 Build Targeted List', prompt: '@Talent Lead Gen Agent: Build a target list of 20 VP Engineering profiles at Series A AI startups' }
        ]
      },
      {
        id: 'proposal_closing',
        name: 'Proposal & Scope Strategist',
        dept: 'Sales · Closing & Deals',
        desc: 'Converts client discovery calls into high-ticket $5k-$10k proposals with structured deliverables, pricing tiers, and timelines.',
        icon: '💼',
        tags: ['proposal-writer', 'scope-of-work', 'pricing-tiers', 'upwork-pitch'],
        tools: ['HubSpot CRM', 'PandaDoc', 'Stripe'],
        ladder: ['Writing custom PDF proposals by hand', 'Using template placeholders', 'Instant proposal generation from meeting transcripts and pipeline data'],
        actions: [
          { label: '📄 Draft $5k Proposal', prompt: '@Proposal Strategist: Draft a comprehensive $5k freelance proposal for building an AI ATS dashboard' },
          { label: '💡 Generate Pricing Tiers', prompt: '@Proposal Strategist: Create 3-tier value pricing for an AI workflow implementation' }
        ]
      }
    ]
  },
  {
    id: 'deals',
    name: 'DEALS',
    deptTitle: 'DEALS',
    deptSub: 'REPLIES · CALLS · CLOSING · PIPELINE',
    angle: Math.PI * 0.8,
    radius: 270,
    color: '#f43f5e',
    icon: '💼',
    jobs: [
      {
        id: 'deal_pipeline',
        name: 'Pipeline Velocity Tracker',
        dept: 'Deals · CRM Operations',
        desc: 'Audits open deals in HubSpot, detects stalled opportunities exceeding 14 days, and drafts reactivation nudges.',
        tags: ['deal-scoring', 'stalled-deal-nudge', 'pipeline-velocity'],
        tools: ['HubSpot', 'Salesforce', 'Gmail'],
        ladder: ['Manually reviewing CRM deals', 'Setting automated reminder emails', 'AI autonomously reviews deal transcripts and suggests closing leverage'],
        actions: [
          { label: '⚡ Nudge Stalled Deals', prompt: '@Sales Agent: Draft customized reactivation emails for all deals stalled for more than 14 days' },
          { label: '📊 Forecast Pipeline Revenue', prompt: '@Sales Agent: Summarize weighted probability forecast for our current quarter' }
        ]
      }
    ]
  },
  {
    id: 'back_office',
    name: 'BACK OFFICE',
    deptTitle: 'BACK OFFICE',
    deptSub: 'MONEY IN · BOOKS · TAX · RUNWAY',
    angle: Math.PI * 0.2,
    radius: 280,
    color: '#eab308',
    icon: '💰',
    jobs: [
      {
        id: 'controller_guard',
        name: 'Financial Controller & Ledger',
        dept: 'Back Office · Accounting Operations',
        desc: 'Guarantees accounting precision: double-click safety locks, immutable ledger entries, and monthly burn rate reconciliation.',
        tags: ['journal-entries', 'double-click-lock', 'reconciliation', 'audit-trail'],
        tools: ['QuickBooks', 'Xero', 'Stripe Ledger'],
        ladder: ['Exporting CSVs and categorizing manually', 'Rules-based auto-categorization', 'Autonomous reconciliation with human exception approval'],
        actions: [
          { label: '📊 Cash Runway Forecast', prompt: '@Finance Agent: Generate a 6-month cash flow and runway forecast based on current recurring software expenses' },
          { label: '🔍 Audit Recurring Subscriptions', prompt: '@Finance Agent: Scan recent expenses for duplicate software subscriptions and unused licenses' }
        ]
      }
    ]
  },
  {
    id: 'customer',
    name: 'CUSTOMER',
    deptTitle: 'CUSTOMER',
    deptSub: 'SUPPORT · SUCCESS · COMMUNITY',
    angle: Math.PI * 1.85,
    radius: 260,
    color: '#ec4899',
    icon: '🤝',
    jobs: [
      {
        id: 'ticket_triage',
        name: 'Customer Support Triage',
        dept: 'Customer · Helpdesk',
        desc: 'Classifies inbound user tickets, extracts sentiment, matches documentation, and drafts instant verified solutions.',
        tags: ['support-triage', 'sentiment-analysis', 'faq-matching'],
        tools: ['Zendesk', 'Intercom', 'Linear'],
        ladder: ['Answering every ticket manually', 'Generic bot with keyword triggers', 'Autonomous agent resolving 70% of tier-1 issues with zero latency'],
        actions: [
          { label: '📥 Triage Support Tickets', prompt: '@Email Agent: Categorize latest user feedback tickets by urgency and sentiment' },
          { label: '📘 Draft FAQ Article', prompt: '@Research Agent: Compile an FAQ section addressing common onboarding bottlenecks' }
        ]
      }
    ]
  },
  {
    id: 'intelligence',
    name: 'INTELLIGENCE',
    deptTitle: 'INTELLIGENCE',
    deptSub: 'COMPANIES · PEOPLE · MARKETS',
    angle: Math.PI * 1.6,
    radius: 270,
    color: '#06b6d4',
    icon: '🔬',
    jobs: [
      {
        id: 'market_intel',
        name: 'Competitor Intelligence Radar',
        dept: 'Intelligence · Market Research',
        desc: 'Scrapes competitor feature releases, pricing updates, and public reviews to identify market gaps and product opportunities.',
        tags: ['competitor-tracking', 'pricing-scrape', 'market-positioning'],
        tools: ['Perplexity', 'SerpAPI', 'BrightData'],
        ladder: ['Checking competitor websites periodically', 'Google Alerts', 'Autonomous intelligence agent monitoring competitor changelogs daily'],
        actions: [
          { label: '🔍 Compare Competitor Features', prompt: '@Research Agent: Analyze top 3 competitors in AI ATS recruitment and highlight missing features' },
          { label: '📊 Market Gap Analysis', prompt: '@Research Agent: Summarize current pricing trends in autonomous AI agents' }
        ]
      }
    ]
  },
  {
    id: 'operations',
    name: 'OPERATIONS',
    deptTitle: 'OPERATIONS',
    deptSub: 'ONBOARDING · BUILDS · CLIENT OPS',
    angle: Math.PI * 1.5,
    radius: 290,
    color: '#10b981',
    icon: '⚙️',
    jobs: [
      {
        id: 'autonomous_patrol',
        name: 'Autonomous Workspace Patrol',
        dept: 'Operations · System Health',
        desc: 'Rotates oversized log files (>2MB), prunes stale Python cache clutter, and catches algorithmic nested loop regressions.',
        tags: ['cache-prune', 'log-rotate', 'ast-lint', '6h-daemon'],
        tools: ['ZERO Daemon', 'Python AST', 'FileSystem API'],
        ladder: ['Fixing disk bloat when disk is full', 'Writing bash cron scripts', 'Autonomous patrol daemon sweeping 11 projects every 6 hours with HITL approvals'],
        actions: [
          { label: '⚡ Rotate Oversized Logs', prompt: '@Autonomous Optimization Architect: Rotate and truncate all logs exceeding 2MB across projects' },
          { label: '🧹 Prune Stale Cache', prompt: '@Autonomous Optimization Architect: Clean up stale __pycache__ and pytest artifacts' }
        ]
      },
      {
        id: 'quant_trading',
        name: 'Quant Trading SMC Engine',
        dept: 'Operations · Financial Markets',
        desc: 'Autonomous MT5 broker connection executing Smart Money Concept confluence (M5 Liquidity Sweeps, MSS, FVG Retests) with dynamic trailing stops.',
        tags: ['mt5-bridge', 'smc-confluence', 'trailing-stop', 'circuit-breaker'],
        tools: ['MetaTrader 5', 'Vantage Broker', 'SMC Scanner'],
        ladder: ['Manual chart staring', 'Fixed pip stop loss EA', 'AI SMC Confluence with breakeven lock at +0.50R and strict $30 daily risk ceiling'],
        actions: [
          { label: '📈 Audit SMC Confluence', prompt: '@Trading Agent: Summarize last scanned M5 candle, liquidity sweeps, and setup score' },
          { label: '🛡️ Check Trailing Stop', prompt: '@Trading Agent: Verify trailing stop status on open MT5 positions' },
          { label: '⚡ Review Risk Limits', prompt: '@Trading Coach: Audit today\'s risk exposure and daily loss limits' }
        ]
      },
      {
        id: 'hr_recruitment',
        name: 'HR Recruitment Assistant ATS',
        dept: 'Operations · Talent & HR',
        desc: 'Complete enterprise recruitment system: Public Careers Portal, Self-Service Interview Booking, Dynamic Offer Letter Generator, and GDPR Blind Hiring.',
        tags: ['candidate-rag', 'interview-copilot', 'careers-portal', 'gdpr-privacy'],
        tools: ['Streamlit 8501', 'ChromaDB', 'SendGrid'],
        ladder: ['Reviewing resumes by hand', 'Keyword search filter', 'Semantic RAG candidate matching with live conversational Interview Copilot'],
        actions: [
          { label: '🎤 Launch Interview Copilot', prompt: '@AI Recruiter: Open interview copilot brief for Senior Full-Stack Engineer' },
          { label: '📜 Generate Offer Letter', prompt: '@Loop Engineering Agent: Generate customized offer letter contract with e-sign tracking' },
          { label: '🙈 Blind Screening Mode', prompt: '@AI Recruiter: Anonymize candidate PII for unbiased interview evaluations' }
        ]
      }
    ]
  }
];

// Switch between [ MAP ] [ DASHBOARDS ] [ CHART ]
function switchNeuralTab(tabName) {
  playSound('blip');
  currentNeuralTab = tabName;

  document.querySelectorAll('.st-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.id === `tab-btn-${tabName}`);
  });

  // Explicit inline style switching to guarantee complete view isolation
  document.querySelectorAll('.st-view-container').forEach(view => {
    view.classList.remove('active');
    view.style.display = 'none';
  });

  const activeView = document.getElementById(`st-${tabName}-view`);
  if (activeView) {
    activeView.classList.add('active');
    activeView.style.display = 'flex';
  }

  if (tabName === 'map') {
    startNeuralBrainCanvas();
  } else {
    stopNeuralBrainCanvas();
    if (tabName === 'dashboards') {
      updateCoverflow();
    } else if (tabName === 'chart') {
      renderRolloutMatrix(currentChartDept);
    }
  }
}

// Open/Close Modal
function toggleSkillTree(open) {
  const modal = document.getElementById('skill-tree-modal');
  if (!modal) return;
  if (open) {
    playSound('blip');
    modal.classList.add('active');
    switchNeuralTab('map'); // Always opens directly to the pure Living Brain Map
  } else {
    playSound('blip');
    modal.classList.remove('active');
    stopNeuralBrainCanvas();
  }
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const dossier = document.getElementById('st-dossier-drawer');
    if (dossier && dossier.classList.contains('active')) {
      closeDossier();
    } else {
      toggleSkillTree(false);
    }
  }
});

// ==========================================================================
// VIEW 1: LIVING CANVAS NEURAL BRAIN SIMULATION
// ==========================================================================

let canvasParticles = [];
let canvasNodes = [];
let panOffset = { x: 0, y: 0 };
let canvasZoom = 1.0;
let isPanning = false;
let startPan = { x: 0, y: 0 };
let hoveredNode = null;

function initCanvasParticles() {
  canvasParticles = [];
  // Monochrome luxury celestial palette: white, bright light grey, and medium grey
  const starColors = ['#ffffff', '#f8fafc', '#f1f5f9', '#e2e8f0', '#cbd5e1', '#94a3b8', '#64748b'];
  for (let i = 0; i < 140; i++) {
    const angle = Math.random() * Math.PI * 2;
    const dist = Math.random() * 90;
    canvasParticles.push({
      x: Math.cos(angle) * dist,
      y: Math.sin(angle) * dist,
      baseDist: dist,
      angle: angle,
      speed: 0.002 + Math.random() * 0.005,
      size: 1 + Math.random() * 2,
      color: starColors[Math.floor(Math.random() * starColors.length)],
      alpha: 0.35 + Math.random() * 0.65
    });
  }
}

let deptsOpen = true;
let expandedDeptId = null;
let hasDragged = false;
let downPos = { x: 0, y: 0 };

// Ensure 7 departments are perfectly distributed at 360 / 7 = 51.4 degrees with Operations at top (-Math.PI / 2)
function normalizeDeptAngles() {
  const order = ['operations', 'intelligence', 'customer', 'back_office', 'sales', 'deals', 'marketing'];
  const step = (Math.PI * 2) / order.length;
  NEURAL_ORG_DATA.forEach(dept => {
    const idx = order.indexOf(dept.id);
    if (idx !== -1) {
      dept.angle = -Math.PI / 2 + idx * step;
    }
  });
}
normalizeDeptAngles();

function collapseAllToZero() {
  if (expandedDeptId !== null || deptsOpen) {
    playSound('blip');
    expandedDeptId = null;
    deptsOpen = false;
    const drawer = document.getElementById('st-dossier-drawer');
    if (drawer && drawer.classList.contains('active')) {
      closeDossier();
    }
  }
}

function handleNodeClick(node) {
  if (node.isZeroCore) {
    playSound('blip');
    if (!deptsOpen) {
      // If currently collapsed, open the 7 departments!
      deptsOpen = true;
      expandedDeptId = null;
    } else if (expandedDeptId) {
      // If a department is expanded, collapse back to clean 7 departments
      expandedDeptId = null;
    } else {
      // If clean 7 departments are open, collapse everything into ZERO Core
      deptsOpen = false;
    }
    return;
  }

  if (node.isDept) {
    playSound('blip');
    // Toggle expansion of this specific department!
    if (expandedDeptId === node.id) {
      expandedDeptId = null; // collapse back to clean 7 departments
    } else {
      expandedDeptId = node.id; // expand this department with staggered non-clustering fan
    }
    return;
  }

  // Specialist / sub-job node -> Open Dossier Drawer!
  openDossier(node);
}

function startNeuralBrainCanvas() {
  const canvas = document.getElementById('st-brain-canvas');
  if (!canvas) return;

  const resize = () => {
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
  };
  resize();
  window.addEventListener('resize', resize);

  initCanvasParticles();

  // Mouse Wheel Smooth Centered Zoom (zooms towards mouse focal point)
  canvas.onwheel = (e) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const zoomDelta = e.deltaY < 0 ? 0.12 : -0.12;
    zoomCanvas(zoomDelta, mouseX, mouseY);
  };

  // Canvas Mouse Events (Pan & Click)
  canvas.onmousedown = (e) => {
    isPanning = true;
    hasDragged = false;
    downPos = { x: e.clientX, y: e.clientY };
    startPan = { x: e.clientX - panOffset.x, y: e.clientY - panOffset.y };
  };

  window.onmousemove = (e) => {
    if (isPanning) {
      if (Math.hypot(e.clientX - downPos.x, e.clientY - downPos.y) > 6) {
        hasDragged = true;
      }
      panOffset.x = e.clientX - startPan.x;
      panOffset.y = e.clientY - startPan.y;
    }
    checkNodeHover(e, canvas);
  };

  window.onmouseup = () => {
    if (isPanning && !hasDragged) {
      if (hoveredNode) {
        handleNodeClick(hoveredNode);
      } else {
        // User clicked in empty space -> collapse everything into ZERO!
        collapseAllToZero();
      }
    }
    isPanning = false;
  };

  if (!neuralCanvasAnimId) {
    const loop = (t) => {
      drawNeuralBrain(canvas, t);
      neuralCanvasAnimId = requestAnimationFrame(loop);
    };
    neuralCanvasAnimId = requestAnimationFrame(loop);
  }
}

function stopNeuralBrainCanvas() {
  if (neuralCanvasAnimId) {
    cancelAnimationFrame(neuralCanvasAnimId);
    neuralCanvasAnimId = null;
  }
}

function checkNodeHover(e, canvas) {
  const rect = canvas.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  let found = null;
  for (const node of canvasNodes) {
    const dist = Math.hypot(mouseX - node.screenX, mouseY - node.screenY);
    if (dist <= node.radius + 6) {
      found = node;
      break;
    }
  }

  if (found !== hoveredNode) {
    hoveredNode = found;
    canvas.style.cursor = hoveredNode ? 'pointer' : 'grab';
    if (hoveredNode) playSound('blip');
  }
}

function drawNeuralBrain(canvas, time) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  const cx = w / 2 + panOffset.x;
  const cy = h / 2 + panOffset.y;

  ctx.clearRect(0, 0, w, h);
  canvasNodes = [];

  // Organic floating physics & balanced medium proportions
  const breath = Math.sin(time * 0.0018) * 3;
  const deptBaseRadius = 165 * canvasZoom; // Medium balanced ring

  // 1. Register ZERO Core in central hub
  const isZeroHover = hoveredNode && hoveredNode.isZeroCore;
  const zeroR = (25 + (isZeroHover ? 3 : 0)) * canvasZoom;

  canvasNodes.push({
    id: 'zero_core',
    name: 'ZERO CORE',
    screenX: cx,
    screenY: cy,
    radius: zeroR,
    isZeroCore: true
  });

  // 2. Draw Central Starry Particle Galaxy
  canvasParticles.forEach((p) => {
    p.angle += p.speed;
    const pDist = p.baseDist * 0.65 * canvasZoom;
    const px = cx + Math.cos(p.angle) * pDist;
    const py = cy + Math.sin(p.angle) * pDist;

    ctx.beginPath();
    ctx.arc(px, py, p.size * canvasZoom, 0, Math.PI * 2);
    ctx.fillStyle = p.color;
    ctx.globalAlpha = p.alpha * (0.6 + Math.sin(time * 0.003 + p.angle) * 0.4);
    ctx.fill();
    ctx.globalAlpha = 1.0;
  });

  // If departments are collapsed into ZERO, show hint and return early
  if (!deptsOpen) {
    renderZeroCoreVisual(ctx, cx, cy, zeroR, isZeroHover, false);
    ctx.font = `${Math.round(8.5 * canvasZoom)}px "JetBrains Mono", monospace`;
    ctx.fillStyle = '#38bdf8';
    ctx.textAlign = 'center';
    ctx.fillText('✦ CLICK ZERO TO OPEN DEPARTMENTS ✦', cx, cy + zeroR + 24 * canvasZoom);
    return;
  }

  // 3. Draw Active Department Faint Watermark (Centered in background, NO text overlap!)
  if (expandedDeptId) {
    const activeDept = NEURAL_ORG_DATA.find(d => d.id === expandedDeptId);
    if (activeDept) {
      ctx.save();
      ctx.font = `bold ${Math.round(48 * canvasZoom)}px "Cinzel", "Marcellus", serif`;
      ctx.fillStyle = 'rgba(255, 255, 255, 0.028)';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(activeDept.name, cx, cy - 90 * canvasZoom);
      ctx.restore();
    }
  }

  // 4. Draw Department Nodes & Connected Sub-Jobs
  NEURAL_ORG_DATA.forEach((dept) => {
    const isExpanded = expandedDeptId === dept.id;
    const isDeptHover = hoveredNode && hoveredNode.id === dept.id;
    const isDimmed = expandedDeptId && !isExpanded; // Focus mode: dim other departments

    // Gentle organic floating drift
    const floatX = Math.cos(time * 0.0012 + dept.angle * 2.5) * 4 * canvasZoom;
    const floatY = Math.sin(time * 0.0015 + dept.angle * 2.5) * 4 * canvasZoom;

    const deptDist = deptBaseRadius + breath;
    const deptX = cx + Math.cos(dept.angle) * deptDist + floatX;
    const deptY = cy + Math.sin(dept.angle) * deptDist + floatY;

    // Curved Axon Filament from ZERO Core to Department
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    const midX = (cx + deptX) / 2 + Math.sin(dept.angle) * 12 * canvasZoom;
    const midY = (cy + deptY) / 2 - Math.cos(dept.angle) * 12 * canvasZoom;
    ctx.quadraticCurveTo(midX, midY, deptX, deptY);
    ctx.strokeStyle = isExpanded ? dept.color + 'bb' : (isDimmed ? dept.color + '18' : dept.color + '45');
    ctx.lineWidth = (isExpanded ? 2.2 : 1.2) * canvasZoom;
    ctx.stroke();

    // Register Department Node
    const deptRadius = (18 + (isDeptHover ? 3 : 0)) * canvasZoom;
    canvasNodes.push({
      id: dept.id,
      name: dept.name,
      deptTitle: dept.deptTitle,
      deptSub: dept.deptSub,
      color: dept.color,
      icon: dept.icon,
      screenX: deptX,
      screenY: deptY,
      radius: deptRadius,
      isDept: true,
      isExpanded: isExpanded,
      isDimmed: isDimmed,
      data: (dept.allAgents && dept.allAgents[0]) || dept.jobs[0]
    });

    // 5. IF EXPANDED: Bloom sub-agent nodes with STAGGERED non-clustering distances!
    if (isExpanded) {
      const activeJobs = (dept.allAgents && dept.allAgents.length > 0) ? dept.allAgents.slice(0, 5) : dept.jobs;
      const jobCount = activeJobs.length;
      const spreadAngleTotal = Math.PI * 0.75; // Wide ~135 degree fan arc

      activeJobs.forEach((job, idx) => {
        const offsetAngle = (idx - (jobCount - 1) / 2) * (spreadAngleTotal / Math.max(1, jobCount - 1));
        const subAngle = dept.angle + offsetAngle;

        // Radial Stagger: alternate distances (85px vs 140px) so labels NEVER collide!
        const isOuterStagger = idx % 2 !== 0;
        const subDist = (isOuterStagger ? 138 : 88) * canvasZoom;

        const subFloatX = Math.cos(time * 0.002 + idx) * 3 * canvasZoom;
        const subFloatY = Math.sin(time * 0.0022 + idx) * 3 * canvasZoom;

        const jobX = deptX + Math.cos(subAngle) * subDist + subFloatX;
        const jobY = deptY + Math.sin(subAngle) * subDist + subFloatY;

        // Clean connector synapse
        ctx.beginPath();
        ctx.moveTo(deptX, deptY);
        ctx.lineTo(jobX, jobY);
        ctx.strokeStyle = dept.color + '85';
        ctx.lineWidth = 1.2 * canvasZoom;
        ctx.stroke();

        // Tiny copper accent dot attached by thin connector line (Altari signature)
        const accentAngle = subAngle + 0.35;
        const accentDist = 15 * canvasZoom;
        const accentX = jobX + Math.cos(accentAngle) * accentDist;
        const accentY = jobY + Math.sin(accentAngle) * accentDist;

        ctx.beginPath();
        ctx.moveTo(jobX, jobY);
        ctx.lineTo(accentX, accentY);
        ctx.strokeStyle = 'rgba(217, 119, 6, 0.45)';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(accentX, accentY, 2.5 * canvasZoom, 0, Math.PI * 2);
        ctx.fillStyle = '#d97706';
        ctx.fill();

        canvasNodes.push({
          id: job.id,
          name: job.name,
          color: dept.color,
          screenX: jobX,
          screenY: jobY,
          radius: 13 * canvasZoom,
          isDept: false,
          icon: job.icon || '📄',
          data: job
        });
      });
    }
  });

  // 6. Render Visuals for All Nodes
  canvasNodes.forEach((node) => {
    const isHover = hoveredNode && hoveredNode.id === node.id;
    const r = node.radius;

    if (node.isZeroCore) {
      renderZeroCoreVisual(ctx, node.screenX, node.screenY, r, isHover, true);
    } else if (node.isDept) {
      // Department Hub Node
      const alpha = node.isDimmed ? 0.2 : 1.0;
      ctx.save();
      ctx.globalAlpha = alpha;

      ctx.beginPath();
      ctx.arc(node.screenX, node.screenY, r, 0, Math.PI * 2);
      ctx.fillStyle = node.isExpanded ? node.color + '35' : (isHover ? '#1e293b' : '#0e1628');
      ctx.fill();
      ctx.lineWidth = node.isExpanded ? 2.5 : (isHover ? 2.2 : 1.6);
      ctx.strokeStyle = node.color;
      ctx.stroke();

      // Icon inside department node
      ctx.font = `${Math.round(11 * canvasZoom)}px sans-serif`;
      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(node.icon || '⚙️', node.screenX, node.screenY);

      if (isHover || node.isExpanded) {
        ctx.beginPath();
        ctx.arc(node.screenX, node.screenY, r + 6, 0, Math.PI * 2);
        ctx.strokeStyle = node.color + '70';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // Department Label
      ctx.font = `bold ${Math.round(9 * canvasZoom)}px "Cinzel", "Orbitron", sans-serif`;
      ctx.fillStyle = (isHover || node.isExpanded) ? '#ffffff' : '#e2e8f0';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'alphabetic';
      ctx.fillText(node.name, node.screenX, node.screenY + r + (12 * canvasZoom));

      // Indicator pill: click to expand / active indicator
      ctx.font = `${Math.round(6.5 * canvasZoom)}px "JetBrains Mono", monospace`;
      ctx.fillStyle = node.isExpanded ? '#38bdf8' : '#64748b';
      const indicatorText = node.isExpanded ? '▲ ACTIVE' : '▾ OPEN';
      ctx.fillText(indicatorText, node.screenX, node.screenY + r + (20 * canvasZoom));
      ctx.restore();

    } else {
      // Ivory Pill Sub-Job Node (Altari Signature)
      ctx.beginPath();
      ctx.arc(node.screenX, node.screenY, r, 0, Math.PI * 2);
      ctx.fillStyle = isHover ? '#ffffff' : '#f4f1ea';
      ctx.fill();
      ctx.lineWidth = isHover ? 2.2 : 1.4;
      ctx.strokeStyle = isHover ? '#38bdf8' : '#334155';
      ctx.stroke();

      if (isHover) {
        ctx.beginPath();
        ctx.arc(node.screenX, node.screenY, r + 5, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.6)';
        ctx.lineWidth = 1.4;
        ctx.stroke();
      }

      // Icon inside ivory pill
      ctx.font = `${Math.round(9 * canvasZoom)}px sans-serif`;
      ctx.fillStyle = '#0f172a';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(node.icon || '📄', node.screenX, node.screenY);

      // Clean label badge with background pill (guarantees ZERO overlap)
      const labelText = node.name;
      ctx.font = `${Math.round(7.5 * canvasZoom)}px "Inter", sans-serif`;
      const textWidth = ctx.measureText(labelText).width;
      const pillPadX = 6;
      const pillH = 14 * canvasZoom;
      const pillW = textWidth + pillPadX * 2;
      const pillX = node.screenX - pillW / 2;
      const pillY = node.screenY + r + 3 * canvasZoom;

      ctx.fillStyle = isHover ? 'rgba(15, 23, 42, 0.95)' : 'rgba(10, 15, 26, 0.88)';
      ctx.beginPath();
      ctx.roundRect(pillX, pillY, pillW, pillH, 3);
      ctx.fill();
      ctx.strokeStyle = isHover ? '#38bdf8' : 'rgba(255, 255, 255, 0.12)';
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.fillStyle = isHover ? '#38bdf8' : '#f1f5f9';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(labelText, node.screenX, pillY + pillH / 2);
    }
  });
}

function renderZeroCoreVisual(ctx, x, y, r, isHover, showStatus) {
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = isHover ? 'rgba(30, 41, 59, 0.98)' : 'rgba(15, 23, 42, 0.95)';
  ctx.fill();
  ctx.lineWidth = isHover ? 2.5 : 1.8;
  ctx.strokeStyle = isHover ? '#38bdf8' : 'rgba(56, 189, 248, 0.6)';
  ctx.stroke();

  if (isHover) {
    ctx.beginPath();
    ctx.arc(x, y, r + 6, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.4)';
    ctx.lineWidth = 1.2;
    ctx.stroke();
  }

  ctx.font = `bold ${Math.round(8.5 * canvasZoom)}px "Orbitron", sans-serif`;
  ctx.fillStyle = '#38bdf8';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('ZERO', x, y - (3 * canvasZoom));

  ctx.font = `${Math.round(6 * canvasZoom)}px "JetBrains Mono", monospace`;
  ctx.fillStyle = '#94a3b8';
  const sub = expandedDeptId ? 'COLLAPSE' : (deptsOpen ? 'CORE OS' : 'EXPAND');
  ctx.fillText(sub, x, y + (6 * canvasZoom));
}

// Canvas Zoom Controls (Smooth, Clamped & Center-Focused)
function zoomCanvas(delta, focalX, focalY) {
  const canvas = document.getElementById('st-brain-canvas');
  const w = canvas ? canvas.width : window.innerWidth;
  const h = canvas ? canvas.height : window.innerHeight;
  const fx = focalX !== undefined ? focalX : w / 2;
  const fy = focalY !== undefined ? focalY : h / 2;

  const oldZoom = canvasZoom;
  const newZoom = Math.min(2.5, Math.max(0.45, Math.round((canvasZoom + delta) * 100) / 100));
  if (oldZoom === newZoom) return;

  // Zoom centered on focal point
  panOffset.x = fx - (fx - panOffset.x) * (newZoom / oldZoom);
  panOffset.y = fy - (fy - panOffset.y) * (newZoom / oldZoom);
  canvasZoom = newZoom;

  const el = document.getElementById('st-zoom-val');
  if (el) el.textContent = `${Math.round(canvasZoom * 100)}%`;
}

function resetCanvasZoom() {
  canvasZoom = 1.0;
  panOffset = { x: 0, y: 0 };
  const el = document.getElementById('st-zoom-val');
  if (el) el.textContent = '100%';
}

// Open Altari-Style Dossier Drawer
function openDossier(node) {
  const drawer = document.getElementById('st-dossier-drawer');
  if (!drawer) return;
  playSound('approve');

  const job = node.data || {};
  currentDossierSkill = job;

  // Title & Status
  const badge = document.getElementById('dossier-status-badge');
  if (badge) badge.textContent = job.status || 'FULLY AUTONOMOUS';

  const title = document.getElementById('dossier-title');
  if (title) title.textContent = job.name || node.name || 'Autonomous Specialist';

  const dept = document.getElementById('dossier-dept');
  if (dept) dept.textContent = job.dept || 'Operations · Core Intelligence';

  const desc = document.getElementById('dossier-desc');
  if (desc) desc.textContent = job.desc || 'Autonomous specialized capability mapped in ZERO Neural Mesh.';

  // Breaks Into Tags
  const tagRow = document.getElementById('dossier-tags');
  if (tagRow) {
    tagRow.innerHTML = '';
    (job.tags || ['comment-harvester', 'engagement-miner', 'profile-collector']).forEach(t => {
      const s = document.createElement('span');
      s.className = 'dossier-tag';
      s.textContent = t;
      tagRow.appendChild(s);
    });
  }

  // Wired Into Tools
  const toolRow = document.getElementById('dossier-tools');
  if (toolRow) {
    toolRow.innerHTML = '';
    (job.tools || ['Apify', 'HeyReach', 'LinkedIn API', 'ZERO Core']).forEach(t => {
      const s = document.createElement('span');
      s.className = 'dossier-tag';
      s.textContent = t;
      toolRow.appendChild(s);
    });
  }

  // Builds On
  const buildsOn = document.getElementById('dossier-builds-on');
  if (buildsOn) {
    buildsOn.innerHTML = `<span class="dossier-tag">${job.buildsOn || 'ICP Definition'}</span>`;
  }

  // What It Replaces
  const replaces = document.getElementById('dossier-replaces');
  if (replaces) {
    replaces.textContent = job.replaces || 'The list nobody builds by hand: everyone who engaged with a competitor\'s post is a warm prospect, but scraping them manually takes hours per post.';
  }

  // The Ladder
  const ladderHumanLed = document.getElementById('ladder-human-led');
  if (ladderHumanLed) ladderHumanLed.textContent = (job.ladder && job.ladder[0]) || 'You screenshot commenters and look them up one by one.';

  const ladderHumanAssisted = document.getElementById('ladder-human-assisted');
  if (ladderHumanAssisted) ladderHumanAssisted.textContent = (job.ladder && job.ladder[1]) || 'Point the agent at a post or profile; it harvests engagers, enriches, scores against ICP, and drafts the first DM.';

  const ladderAutonomous = document.getElementById('ladder-autonomous');
  if (ladderAutonomous) ladderAutonomous.textContent = (job.ladder && job.ladder[2]) || 'Watched accounts and keywords feed a standing warm-prospect pool, refreshed continuously.';

  // The Human
  const humanBox = document.getElementById('dossier-human');
  if (humanBox) {
    humanBox.textContent = job.humanGuidance || 'AI owns the work. A human audits outputs on a cadence and owns the strategy it executes · directing, not doing.';
  }

  // Build Notes
  const buildNotes = document.getElementById('dossier-build-notes');
  if (buildNotes) {
    buildNotes.textContent = job.buildNotes || 'Highest-intent cold list you can build · these people already raised their hand on the topic. The skill below scrapes engagers, enriches profiles, ICP-scores, and writes openers in one pass.';
  }

  // Segmented Status Control
  setSkillStatus('LIVE', false);

  // Render Action Buttons
  const actionsContainer = document.getElementById('dossier-actions');
  if (actionsContainer) {
    actionsContainer.innerHTML = '';
    const actions = job.actions || [
      { label: '⚡ Run Strategic Audit', prompt: `@Autonomous Optimization Architect: Audit ${job.name} execution parameters` }
    ];

    actions.forEach((act, idx) => {
      const btn = document.createElement('button');
      btn.className = `btn-dossier-action ${idx === 0 ? 'primary' : ''}`;
      btn.innerHTML = `<span>${act.label}</span> ➔`;
      btn.onclick = () => executeDossierAction(act.prompt);
      actionsContainer.appendChild(btn);
    });
  }

  // Reset output feed
  const feed = document.getElementById('dossier-output-feed');
  if (feed) {
    feed.style.display = 'none';
    feed.textContent = '';
  }

  drawer.classList.add('active');
}

function closeDossier() {
  const drawer = document.getElementById('st-dossier-drawer');
  if (drawer) drawer.classList.remove('active');
}

function setSkillStatus(status, notify = true) {
  if (notify) playSound('blip');
  const badge = document.getElementById('dossier-status-badge');
  if (badge) badge.textContent = status;

  ['not-started', 'in-dev', 'live'].forEach(id => {
    const btn = document.getElementById(`seg-${id}`);
    if (btn) btn.classList.remove('active');
  });

  if (status === 'NOT STARTED') {
    document.getElementById('seg-not-started')?.classList.add('active');
  } else if (status === 'IN DEVELOPMENT') {
    document.getElementById('seg-in-dev')?.classList.add('active');
  } else {
    document.getElementById('seg-live')?.classList.add('active');
  }
}

function previewSkillManifest() {
  playSound('blip');
  const feed = document.getElementById('dossier-output-feed');
  if (!feed) return;
  feed.style.display = 'block';

  const skillName = currentDossierSkill?.name ? currentDossierSkill.name.toLowerCase().replace(/[^a-z0-9]+/g, '-') : 'specialist-skill';
  feed.textContent = `---
# ZERO RUNNABLE SKILL MANIFEST
skill_id: "zero-${skillName}"
version: "2.4.0"
execution_engine: "zero_core.orchestrator"
autonomy_level: "Tier-3 / Fully Autonomous"
schedule: "cron(0 */2 * * *)" # Every 2 hours
wired_integrations:
  - id: "${currentDossierSkill?.tools?.[0] || 'FastAPI'}"
    auth: "SECURE_VAULT_KEY"
  - id: "${currentDossierSkill?.tools?.[1] || 'ZERO_DATABASE'}"
ladder_policy:
  human_approval_required: false
  max_retry: 3
  circuit_breaker_threshold: "0.05 failure rate"
---
[✓ Skill file active & synced with ZERO Neural Mesh]`;
}

// Execute Actionable Dossier Button
async function executeDossierAction(promptText) {
  playSound('blip');
  const feed = document.getElementById('dossier-output-feed');
  if (feed) {
    feed.style.display = 'block';
    feed.textContent = `[*] Dispatching directive to ZERO Orchestrator:\n${promptText}\n\n[Processing...]`;
  }

  try {
    const res = await fetch('/api/task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task: promptText, auto_invoke_llm: true }),
    });
    let data;
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      data = await res.json();
    } else {
      const rawText = await res.text();
      data = {
        selected: { name: 'ZERO Core' },
        answer: res.ok ? rawText : `⚠️ Server Error (${res.status}): ${rawText || res.statusText}`,
        status: res.ok ? 'SUCCESS' : 'ERROR',
      };
    }
    playSound(res.ok ? 'approve' : 'alert');

    if (feed) {
      feed.textContent = `[✓ Task Executed Successfully]\n\n` + (data.answer || JSON.stringify(data, null, 2));
    }
  } catch (err) {
    if (feed) feed.textContent = `[Error executing task]: ${err.message}`;
  }
}

// Convenience helper for direct prompts
function executeCustomPrompt(promptText) {
  toggleSkillTree(false);
  sendPrompt(promptText);
}

// ==========================================================================
// VIEW 2: 3D COVERFLOW COMMAND CENTERS CAROUSEL
// ==========================================================================

function navigateToDashboardPage(idx) {
  playSound('approve');
  switch (idx) {
    case 0:
      // Card 0: Meta Ads & Paid Acquisition -> Live SaaS & Growth Portal
      window.open('/saas-website', '_blank');
      break;
    case 1:
      // Card 1: HubSpot Sales Pipeline -> Live Sales CRM Pipeline API & telemetry
      window.open('/api/v1/sales/pipeline', '_blank');
      break;
    case 2:
      // Card 2: Quant Trading Terminal (MT5 SMC) -> Live Trading State & Candle Feed
      window.open('/api/trading/status', '_blank');
      break;
    case 3:
      // Card 3: HR Recruitment Assistant ATS -> Live Careers Portal & Candidate Management
      window.open('/saas-website#careers', '_blank');
      break;
    default:
      break;
  }
}

function selectCoverflowCard(idx) {
  if (coverflowIndex === idx) {
    // If the front card is clicked, redirect directly to its respective page!
    navigateToDashboardPage(idx);
    return;
  }
  coverflowIndex = idx;
  playSound('blip');
  updateCoverflow();
}

function rotateCoverflow(delta) {
  const cards = document.querySelectorAll('.cf-card');
  coverflowIndex = Math.max(0, Math.min(cards.length - 1, coverflowIndex + delta));
  playSound('blip');
  updateCoverflow();
}

function updateCoverflow() {
  const cards = document.querySelectorAll('.cf-card');
  cards.forEach((card, i) => {
    const offset = i - coverflowIndex;
    const absOffset = Math.abs(offset);

    if (offset === 0) {
      card.style.transform = `translateX(0px) translateZ(140px) rotateY(0deg)`;
      card.style.opacity = '1';
      card.style.zIndex = '20';
      card.style.pointerEvents = 'auto';
    } else {
      const dir = offset > 0 ? 1 : -1;
      const x = dir * (280 + (absOffset - 1) * 80);
      const z = -140 * absOffset;
      const rotY = dir * -42;
      card.style.transform = `translateX(${x}px) translateZ(${z}px) rotateY(${rotY}deg)`;
      card.style.opacity = `${Math.max(0.3, 0.85 - absOffset * 0.3)}`;
      card.style.zIndex = `${10 - absOffset}`;
      card.style.pointerEvents = 'auto';
    }
  });
}

// Drag Coverflow Handler
const cfDeck = document.getElementById('cf-deck');
if (cfDeck) {
  cfDeck.onmousedown = (e) => {
    isDraggingCoverflow = true;
    startX = e.clientX;
  };
  window.addEventListener('mousemove', (e) => {
    if (!isDraggingCoverflow) return;
    const diff = e.clientX - startX;
    if (Math.abs(diff) > 70) {
      rotateCoverflow(diff > 0 ? -1 : 1);
      startX = e.clientX;
    }
  });
  window.addEventListener('mouseup', () => {
    isDraggingCoverflow = false;
  });
}

// ==========================================================================
// VIEW 3: ALTARI ROLLOUT MATRIX (CHART VIEW)
// ==========================================================================

let currentChartDept = 'sales';

const ROLLOUT_MATRIX_DATA = {
  sales: {
    title: 'Sales · the AI rollout',
    meta: '19 of 22 jobs run autonomously · 3 assisted · the rest stay human.',
    stages: ['Foundation', 'Capture', 'Generate', 'Orchestrate'],
    tiers: [
      {
        id: 'human_led',
        name: 'Human-led',
        desc: 'A person drives it.',
        count: '4 jobs',
        cells: [
          [
            { id: 'offer_pos', name: 'Offer & Positioning', icon: '🎯', stage: 'Ongoing', dept: 'Sales · Strategy' }
          ],
          [
            { id: 'key_acc', name: 'Key-Account Relationships', icon: '🤝', stage: 'Ongoing', dept: 'Sales · Enterprise' }
          ],
          [
            { id: 'brand_voice', name: 'Brand-Voice & Final Approvals', icon: '🛡️', stage: 'Ongoing', dept: 'Sales · Brand' }
          ],
          [
            { id: 'deal_strat', name: 'Deal Strategy on Big Accounts', icon: '📈', stage: 'Ongoing', dept: 'Sales · High-Ticket' }
          ]
        ]
      },
      {
        id: 'human_assisted',
        name: 'Human-assisted',
        desc: 'AI drafts, a human approves.',
        count: '3 jobs',
        cells: [
          [
            { id: 'lookalike', name: 'Lookalike Modeling', icon: '👥', stage: '1 · Foundation •••', dept: 'Sales · Targeting' }
          ],
          [
            { id: 'trigger_det', name: 'Trigger Detection', icon: '🔔', stage: '2 · Capture •••', dept: 'Sales · Signals' }
          ],
          [],
          [
            { id: 'deliverability', name: 'Deliverability & Domain Health', icon: '🛡️', stage: '4 · Orchestrate ••••', dept: 'Sales · Infrastructure' }
          ]
        ]
      },
      {
        id: 'autonomous',
        name: 'Fully autonomous',
        desc: 'AI runs it unattended.',
        count: '19 jobs',
        cells: [
          [
            { id: 'icp_def', name: 'ICP Definition', icon: '🎯', stage: '1 · Foundation •••', dept: 'Sales · Targeting' },
            { id: 'market_map', name: 'Market Mapping', icon: '🌐', stage: '1 · Foundation •••', dept: 'Sales · Research' },
            { id: 'db_mining', name: 'Database Mining', icon: '💾', stage: '1 · Foundation •••', dept: 'Sales · Data' },
            { id: 'web_scraping', name: 'Web & Maps Scraping', icon: '🌪️', stage: '1 · Foundation •••', dept: 'Sales · Lead Gen' },
            { id: 'social_mining', name: 'Social Mining & Prospecting', icon: '👥', stage: '1 · Foundation •••', dept: 'Sales · Social' },
            { id: 'list_build', name: 'List Building', icon: '📑', stage: '1 · Foundation •••', dept: 'Sales · Lists' },
            { id: 'contact_enrich', name: 'Contact Enrichment', icon: '🏢', stage: '1 · Foundation •••', dept: 'Sales · Data' },
            { id: 'email_verif', name: 'Email Verification', icon: '✔️', stage: '1 · Foundation •••', dept: 'Sales · Verification' },
            { id: 'acc_enrich', name: 'Account Enrichment', icon: '🏢', stage: '1 · Foundation •••', dept: 'Sales · Data' },
            { id: 'pers_research', name: 'Personalization Research', icon: '🔍', stage: '1 · Foundation •••', dept: 'Sales · Research' }
          ],
          [
            { id: 'fit_scoring', name: 'Fit Scoring', icon: '📊', stage: '2 · Capture •••', dept: 'Sales · Scoring' }
          ],
          [
            { id: 'cold_email', name: 'Cold Email Drafting', icon: '✍️', stage: '3 · Generate •••', dept: 'Sales · Outreach' },
            { id: 'linkedin_msg', name: 'LinkedIn Messaging', icon: '💬', stage: '3 · Generate •••', dept: 'Sales · Social' },
            { id: 'proof_match', name: 'Proof Matching', icon: '📁', stage: '3 · Generate •••', dept: 'Sales · Proof' },
            { id: 'call_script', name: 'Cold-Call Scripting', icon: '📞', stage: '3 · Generate •••', dept: 'Sales · Scripts' },
            { id: 'video_prospect', name: 'Video Prospecting Prompts', icon: '📹', stage: '3 · Generate •••', dept: 'Sales · Video' },
            { id: 'campaign_launch', name: 'Campaign Launch', icon: '🚀', stage: '3 · Generate •••', dept: 'Sales · Campaigns' }
          ],
          [
            { id: 'camp_orch', name: 'Campaign Orchestration', icon: '⚙️', stage: '4 · Orchestrate ••••', dept: 'Sales · Automation' },
            { id: 'send_opt', name: 'Send Optimization', icon: '⏱️', stage: '4 · Orchestrate ••••', dept: 'Sales · Deliverability' }
          ]
        ]
      }
    ]
  },
  marketing: {
    title: 'Marketing · the AI rollout',
    meta: '16 of 18 jobs run autonomously · 2 assisted · the rest stay human.',
    stages: ['Foundation', 'Capture', 'Generate', 'Orchestrate'],
    tiers: [
      {
        id: 'human_led',
        name: 'Human-led',
        desc: 'A person drives it.',
        count: '2 jobs',
        cells: [
          [{ id: 'brand_narrative', name: 'Brand Narrative & Mission', icon: '💡', stage: 'Ongoing', dept: 'Marketing · Brand' }],
          [],
          [{ id: 'creative_direction', name: 'High-Level Creative Direction', icon: '🎨', stage: 'Ongoing', dept: 'Marketing · Creative' }],
          []
        ]
      },
      {
        id: 'human_assisted',
        name: 'Human-assisted',
        desc: 'AI drafts, a human approves.',
        count: '2 jobs',
        cells: [
          [{ id: 'seo_clusters', name: 'SEO Topic Clusters', icon: '🔍', stage: '1 · Foundation •••', dept: 'Marketing · SEO' }],
          [],
          [{ id: 'ad_copywriting', name: 'Paid Ad Copywriter', icon: '✍️', stage: '3 · Generate •••', dept: 'Marketing · Ads' }],
          []
        ]
      },
      {
        id: 'autonomous',
        name: 'Fully autonomous',
        desc: 'AI runs it unattended.',
        count: '16 jobs',
        cells: [
          [
            { id: 'meta_ad_spend', name: 'Meta Ads Manager & Budget Guard', icon: '📢', stage: '1 · Foundation •••', dept: 'Marketing · Paid Acquisition' },
            { id: 'competitor_spy', name: 'Competitor Ad Creative Miner', icon: '🕵️', stage: '1 · Foundation •••', dept: 'Marketing · Research' }
          ],
          [
            { id: 'fatigue_detection', name: 'Ad Fatigue & Saturation Detector', icon: '📉', stage: '2 · Capture •••', dept: 'Marketing · Analytics' }
          ],
          [
            { id: 'insta_carousel', name: 'Instagram Carousel Outline Builder', icon: '🎨', stage: '3 · Generate •••', dept: 'Marketing · Social' },
            { id: 'email_drip', name: 'Nurture Email Drip Sequence', icon: '📬', stage: '3 · Generate •••', dept: 'Marketing · Email' }
          ],
          [
            { id: 'omni_publisher', name: 'Omni-Channel Auto-Publisher', icon: '🚀', stage: '4 · Orchestrate ••••', dept: 'Marketing · Distribution' }
          ]
        ]
      }
    ]
  },
  operations: {
    title: 'Operations & Engineering · the AI rollout',
    meta: '18 of 20 jobs run autonomously · 2 assisted · the rest stay human.',
    stages: ['Foundation', 'Capture', 'Generate', 'Orchestrate'],
    tiers: [
      {
        id: 'human_led',
        name: 'Human-led',
        desc: 'A person drives it.',
        count: '2 jobs',
        cells: [
          [{ id: 'arch_decisions', name: 'Core System Architecture', icon: '🏛️', stage: 'Ongoing', dept: 'Engineering' }],
          [],
          [],
          [{ id: 'fund_allocations', name: 'Live Fund Allocations', icon: '💰', stage: 'Ongoing', dept: 'Finance' }]
        ]
      },
      {
        id: 'human_assisted',
        name: 'Human-assisted',
        desc: 'AI drafts, a human approves.',
        count: '2 jobs',
        cells: [
          [],
          [{ id: 'hitl_approvals', name: 'HITL Production Approvals', icon: '🛡️', stage: '2 · Capture •••', dept: 'Operations' }],
          [{ id: 'offer_generator', name: 'Dynamic Offer Letter Contract', icon: '📜', stage: '3 · Generate •••', dept: 'HR ATS' }],
          []
        ]
      },
      {
        id: 'autonomous',
        name: 'Fully autonomous',
        desc: 'AI runs it unattended.',
        count: '18 jobs',
        cells: [
          [
            { id: 'workspace_patrol', name: 'Autonomous 11-Project Patrol', icon: '📡', stage: '1 · Foundation •••', dept: 'Operations' },
            { id: 'git_guardian', name: 'Autonomous Git Hygiene & CI', icon: '🐙', stage: '1 · Foundation •••', dept: 'Engineering' }
          ],
          [
            { id: 'smc_scanner', name: 'MT5 SMC Confluence Scanner', icon: '📈', stage: '2 · Capture •••', dept: 'Quant Trading' },
            { id: 'candidate_rag', name: 'HR Candidate Semantic RAG Score', icon: '🧠', stage: '2 · Capture •••', dept: 'HR ATS' }
          ],
          [
            { id: 'interview_copilot', name: 'Live Interview Copilot', icon: '🎤', stage: '3 · Generate •••', dept: 'HR ATS' },
            { id: 'auto_code_repair', name: 'Autonomous Code & Test Repair', icon: '⚡', stage: '3 · Generate •••', dept: 'Engineering' }
          ],
          [
            { id: 'trailing_stop_engine', name: 'Broker Trailing Stop BE+0.50R', icon: '🛡️', stage: '4 · Orchestrate ••••', dept: 'Quant Trading' },
            { id: 'cache_pruner', name: 'Automated Cache & Log Truncator', icon: '🧹', stage: '4 · Orchestrate ••••', dept: 'Operations' }
          ]
        ]
      }
    ]
  }
};

function switchChartDept(deptId) {
  currentChartDept = deptId;
  playSound('blip');

  document.querySelectorAll('.chart-subtab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.textContent.toLowerCase().replace(/\s+/g, '_') === deptId);
  });

  renderRolloutMatrix(deptId);
}

const DEPT_ACTIONS = {
  operations: [
    { label: '⚡ Run Multi-Agent Audit Sweep', prompt: '@Autonomous Optimization Architect: Execute full autonomous multi-agent audit sweep across all 11 projects' },
    { label: '🛡️ Check MT5 SMC Confluence', prompt: '@Trading Agent: Summarize current setup score, open positions, and trailing stop levels' },
    { label: '🧹 Prune Cache Artifacts', prompt: '@Loop Engineering Agent: Prune __pycache__ and clean temporary scratch logs' },
    { label: '📡 Trigger Autonomous Patrol', action: 'triggerPatrol' }
  ],
  sales: [
    { label: '🎯 Harvest 10 ICP Leads', prompt: '@Talent Lead Gen Agent: Source 10 high-intent leads who engaged with recent automation content' },
    { label: '📊 Open Live Sales Pipeline', action: 'openSalesPipeline' },
    { label: '✉️ Draft Cold Enterprise DM', prompt: '@Sales Agent: Write a high-converting, personalized cold email for an Engineering VP' }
  ],
  deals: [
    { label: '⚡ Nudge Stalled Deals', prompt: '@Proposal Strategist: Draft customized follow-up proposals for all sales deals stalled > 14 days' },
    { label: '📄 Draft $5k Proposal Scope', prompt: '@Proposal Strategist: Draft a complete deliverable scope for building an autonomous AI system' }
  ],
  marketing: [
    { label: '✍️ Generate 3 Meta Ad Angles', prompt: '@Marketing Agent: Generate 3 scroll-stopping ad copy variations with viral hooks' },
    { label: '🎨 Outline Instagram Carousel', prompt: '@Marketing Agent: Outline a 5-slide educational carousel with slide-by-slide visual prompts' },
    { label: '🔍 Research SEO Clusters', prompt: '@Marketing Agent: Map top 5 high-intent keyword clusters for AI automation' }
  ],
  intelligence: [
    { label: '🔬 Run Competitor Feature Radar', prompt: '@Research Agent: Run a competitive intelligence scan comparing ZERO vs market alternatives' },
    { label: '📊 Pricing & Margin Analysis', prompt: '@Research Agent: Benchmark SaaS subscription tiers against top agency models' }
  ],
  customer: [
    { label: '📥 Triage Open Inbound Tickets', prompt: '@Email Agent: Triage latest inbound user inquiries and summarize high-priority tickets' },
    { label: '📘 Generate FAQ Guide', prompt: '@Research Agent: Compile comprehensive FAQ answers for common customer onboarding hurdles' }
  ],
  back_office: [
    { label: '💰 Audit SaaS Subscriptions', prompt: '@Finance Agent: Audit current software expenditures and identify unused or duplicate tools' },
    { label: '📊 6-Month Cash Runway Forecast', prompt: '@Finance Agent: Generate a 6-month conservative cash runway projection' }
  ]
};

async function triggerPatrolAudit() {
  playSound('blip');
  try {
    const res = await fetch('/api/patrol/trigger', { method: 'POST' });
    const data = await res.json();
    playSound('approve');
    alert(`[✓ ZERO Autonomous Patrol Triggered]\nStatus: ${data.status || 'Active'}\nMessage: ${data.message || 'Audit sweep dispatched'}`);
  } catch (err) {
    alert(`[!] Patrol trigger error: ${err.message}`);
  }
}

function quickDispatchAgent(agentName) {
  playSound('blip');
  let found = null;
  for (const dept of NEURAL_ORG_DATA) {
    if (dept.jobs) {
      const j = dept.jobs.find(x => x.name.toLowerCase() === agentName.toLowerCase());
      if (j) { found = j; break; }
    }
  }
  if (!found) {
    found = { name: agentName, division: 'operations', role: `${agentName} Specialist` };
  }
  openDossier({ data: found });
  executeCustomPrompt(`@${agentName}: Execute immediate status check and present top 3 actionable recommendations.`);
}

function renderRolloutMatrix(deptId) {
  const body = document.getElementById('chart-matrix-body');
  if (!body) return;

  const data = ROLLOUT_MATRIX_DATA[deptId] || ROLLOUT_MATRIX_DATA['sales'];

  const titleEl = document.getElementById('chart-rollout-title');
  if (titleEl) titleEl.textContent = data.title;

  const subEl = document.getElementById('chart-rollout-subtitle');
  if (subEl) subEl.innerHTML = data.meta;

  // Render Real Department Feature Quick-Run Bar
  const actionBar = document.getElementById('chart-action-bar');
  if (actionBar) {
    actionBar.innerHTML = '';
    const actions = DEPT_ACTIONS[deptId] || [];
    actions.forEach(act => {
      const btn = document.createElement('button');
      btn.className = 'chart-action-btn';
      btn.innerHTML = act.label;
      btn.onclick = () => {
        if (act.action === 'triggerPatrol') {
          triggerPatrolAudit();
        } else if (act.action === 'openSalesPipeline') {
          window.open('/api/v1/sales/pipeline', '_blank');
        } else if (act.prompt) {
          executeCustomPrompt(act.prompt);
        }
      };
      actionBar.appendChild(btn);
    });
  }

  body.innerHTML = '';

  data.tiers.forEach((tier) => {
    const row = document.createElement('div');
    row.className = 'matrix-row';

    // Left Tier Header
    const tierHead = document.createElement('div');
    tierHead.className = 'matrix-tier-header';
    tierHead.innerHTML = `
      <div class="tier-top-info">
        <div class="tier-name">${tier.name}</div>
        <div class="tier-desc">${tier.desc}</div>
      </div>
      <div class="tier-count-badge">${tier.count}</div>
    `;
    row.appendChild(tierHead);

    // 4 Stage Cells
    tier.cells.forEach((cellJobs) => {
      const cell = document.createElement('div');
      cell.className = 'matrix-cell';

      cellJobs.forEach((job) => {
        const card = document.createElement('div');
        card.className = 'matrix-job-card';
        card.onclick = () => openDossier({ data: job });
        const safeName = (job.name || '').replace(/'/g, "\\'");
        card.innerHTML = `
          <div class="mjc-left">
            <div class="mjc-icon">${job.icon || '📄'}</div>
            <div class="mjc-text">
              <div class="mjc-title">${job.name}</div>
              <div class="mjc-stage">${job.stage}</div>
            </div>
          </div>
          <div class="mjc-right">
            <span class="mjc-status-pill">LIVE</span>
            <button class="mjc-run-btn" title="Quick dispatch task to this agent" onclick="event.stopPropagation(); quickDispatchAgent('${safeName}')">⚡ Run</button>
          </div>
        `;
        cell.appendChild(card);
      });

      row.appendChild(cell);
    });

    body.appendChild(row);
  });
}

// ==========================================================================
// DYNAMIC 284-AGENT INTEGRATION ENGINE
// ==========================================================================

function getAgentIcon(division, name) {
  const d = (division || '').toLowerCase();
  const n = (name || '').toLowerCase();
  if (d.includes('security') || n.includes('security') || n.includes('audit')) return '🛡️';
  if (d.includes('finance') || n.includes('finance') || n.includes('tax') || n.includes('ledger') || n.includes('accounting')) return '💰';
  if (d.includes('marketing') || d.includes('paid-media') || n.includes('ad') || n.includes('marketing') || n.includes('copy')) return '📢';
  if (d.includes('design') || n.includes('design') || n.includes('ui') || n.includes('ux') || n.includes('visual')) return '🎨';
  if (d.includes('sales') || n.includes('sales') || n.includes('lead') || n.includes('outreach') || n.includes('prospect')) return '🎯';
  if (d.includes('project') || n.includes('project') || n.includes('manager') || n.includes('deal') || n.includes('pipeline')) return '💼';
  if (d.includes('support') || n.includes('support') || n.includes('customer') || n.includes('triage')) return '🎧';
  if (d.includes('academic') || n.includes('research') || n.includes('scientist') || n.includes('anthropologist')) return '🎓';
  if (d.includes('healthcare') || n.includes('health') || n.includes('medical')) return '🩺';
  if (d.includes('gis') || n.includes('spatial') || n.includes('map')) return '🗺️';
  if (d.includes('game') || n.includes('game')) return '🎮';
  if (d.includes('testing') || n.includes('qa') || n.includes('tester')) return '🧪';
  if (d.includes('engineering') || n.includes('developer') || n.includes('engineer') || n.includes('code') || n.includes('python')) return '💻';
  return '🤖';
}

function agentToJobNode(agent, deptId) {
  const cleanName = agent.name;
  const div = agent.division || 'Native';
  const icon = getAgentIcon(div, cleanName);
  const promptTarget = `@${cleanName}`;
  return {
    id: agent.slug || cleanName.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
    name: cleanName,
    dept: `${deptId.toUpperCase().replace('_', ' ')} · ${div.toUpperCase()}`,
    desc: agent.description || agent.when_to_use || `Specialized autonomous AI specialist active in ZERO Neural Mesh.`,
    icon: icon,
    tags: [div, 'autonomous-agent', ...(agent.keywords || []).slice(0, 2)],
    tools: [div + ' Toolkit', 'Python 3.14', 'ZERO Core API', 'Subagent Router'],
    ladder: [
      `Manual human execution of ${cleanName} responsibilities`,
      `Human-assisted: Prompting generic LLM with manual context assembly`,
      `Fully autonomous: ${promptTarget} running continuously in ZERO Neural Mesh`
    ],
    actions: [
      { label: `⚡ Dispatch ${promptTarget}`, prompt: `${promptTarget}: Analyze current workspace and report execution status` },
      { label: `📋 Generate Scope for ${promptTarget}`, prompt: `${promptTarget}: Outline requirements, deliverables, and architecture for this task` }
    ],
    status: 'FULLY AUTONOMOUS',
    buildsOn: 'ZERO Multi-Agent Protocol',
    replaces: `Manual human specialist hours: ${agent.description || cleanName}`,
    humanGuidance: 'Strategic direction and governance. The agent handles deep domain synthesis and autonomous execution.',
    buildNotes: `Specialist agent from ${div} division. Invokable natively across ZERO or via ${promptTarget}: <instruction>.`
  };
}

function wireAgentsToNeuralSkillTree(agents) {
  if (!agents || !agents.length) return;

  const deptBuckets = {
    marketing: [],
    sales: [],
    deals: [],
    back_office: [],
    customer: [],
    intelligence: [],
    operations: []
  };

  agents.forEach(agent => {
    const div = (agent.division || '').toLowerCase();
    const name = (agent.name || '').toLowerCase();

    let dept = 'operations';
    if (div === 'marketing' || div === 'paid-media' || div === 'design') {
      dept = 'marketing';
    } else if (div === 'sales' || div === 'product' || name.includes('lead') || name.includes('prospect')) {
      dept = 'sales';
    } else if (div === 'project-management' || name.includes('deal') || name.includes('pipeline') || name.includes('scrum')) {
      dept = 'deals';
    } else if (div === 'finance' || name.includes('finance') || name.includes('controller') || name.includes('accounting') || name.includes('tax')) {
      dept = 'back_office';
    } else if (div === 'support' || name.includes('support') || name.includes('customer') || name.includes('community')) {
      dept = 'customer';
    } else if (div === 'academic' || div === 'healthcare' || div === 'specialized' || name.includes('intelligence') || name.includes('research')) {
      dept = 'intelligence';
    } else {
      dept = 'operations';
    }

    deptBuckets[dept].push(agentToJobNode(agent, dept));
  });

  // Assign to NEURAL_ORG_DATA for the canvas
  NEURAL_ORG_DATA.forEach(dept => {
    const bucket = deptBuckets[dept.id] || [];
    if (bucket.length > 0) {
      dept.allAgents = bucket;
      // Show first 5 key agents in the canvas starburst, keep the rest accessible
      dept.jobs = bucket.slice(0, 5);
      dept.deptSub = `${bucket.length} AGENTS WIRED · ${dept.deptSub.split('·')[0] || ''}`;
    }
  });

  // Populate dynamic ROLLOUT_MATRIX_DATA for all 7 departments with REAL agents
  Object.keys(deptBuckets).forEach(deptId => {
    const bucket = deptBuckets[deptId];
    if (!bucket || bucket.length === 0) return;

    bucket.forEach((job, idx) => {
      const mod = idx % 4;
      if (mod === 0) job.stage = '1 · Foundation •••';
      else if (mod === 1) job.stage = '2 · Capture •••';
      else if (mod === 2) job.stage = '3 · Generate •••';
      else job.stage = '4 · Orchestrate ••••';
    });

    const humanLed = bucket.slice(0, Math.min(2, bucket.length)).map(j => ({ ...j, stage: 'Ongoing' }));
    const humanAssisted = bucket.slice(2, Math.min(5, bucket.length));
    const autonomous = bucket.slice(5);

    ROLLOUT_MATRIX_DATA[deptId] = {
      title: `${deptId.toUpperCase().replace('_', ' ')} · the AI rollout`,
      meta: `<span class="highlight-cyan">${bucket.length} of ${bucket.length} agents</span> mapped · <span class="highlight-orange">100% connected</span> to ZERO Neural Mesh.`,
      stages: ['Foundation', 'Capture', 'Generate', 'Orchestrate'],
      tiers: [
        {
          id: 'human_led',
          name: 'Human-led',
          desc: 'High-level strategy & approvals.',
          count: `${humanLed.length} agents`,
          cells: [
            humanLed.filter((_, i) => i % 4 === 0),
            humanLed.filter((_, i) => i % 4 === 1),
            humanLed.filter((_, i) => i % 4 === 2),
            humanLed.filter((_, i) => i % 4 === 3)
          ]
        },
        {
          id: 'human_assisted',
          name: 'Human-assisted',
          desc: 'AI drafts, human reviews.',
          count: `${humanAssisted.length} agents`,
          cells: [
            humanAssisted.filter((_, i) => i % 4 === 0),
            humanAssisted.filter((_, i) => i % 4 === 1),
            humanAssisted.filter((_, i) => i % 4 === 2),
            humanAssisted.filter((_, i) => i % 4 === 3)
          ]
        },
        {
          id: 'autonomous',
          name: 'Fully autonomous',
          desc: 'Agents execute continuously.',
          count: `${autonomous.length} agents`,
          cells: [
            autonomous.filter((_, i) => i % 4 === 0),
            autonomous.filter((_, i) => i % 4 === 1),
            autonomous.filter((_, i) => i % 4 === 2),
            autonomous.filter((_, i) => i % 4 === 3)
          ]
        }
      ]
    };
  });

  // Re-render chart if currently open
  if (currentNeuralTab === 'chart') {
    renderRolloutMatrix(currentChartDept);
  }
}

// Full 284-Agent Real-time Search with Dropdown
function searchNeuralSkills(query) {
  const resultsContainer = document.getElementById('st-search-results');
  if (!resultsContainer) return;

  if (!query || !query.trim()) {
    resultsContainer.style.display = 'none';
    resultsContainer.innerHTML = '';
    return;
  }

  const q = query.toLowerCase().trim();
  const matches = [];

  // Search across all 284 agents
  for (const dept of NEURAL_ORG_DATA) {
    const list = dept.allAgents || dept.jobs || [];
    for (const job of list) {
      if (
        job.name.toLowerCase().includes(q) ||
        (job.desc && job.desc.toLowerCase().includes(q)) ||
        (job.tags && job.tags.some(t => t.toLowerCase().includes(q))) ||
        (job.dept && job.dept.toLowerCase().includes(q))
      ) {
        if (!matches.some(m => m.id === job.id)) {
          matches.push(job);
        }
      }
    }
  }

  if (matches.length === 0) {
    resultsContainer.style.display = 'flex';
    resultsContainer.innerHTML = `
      <div style="padding:12px; font-size:0.75rem; color:#64748b; text-align:center;">
        No agents found matching "${query}"
      </div>
    `;
    return;
  }

  resultsContainer.style.display = 'flex';
  resultsContainer.innerHTML = '';

  matches.slice(0, 12).forEach(match => {
    const item = document.createElement('div');
    item.className = 'st-search-item';
    item.onclick = () => {
      openDossier({ data: match });
      resultsContainer.style.display = 'none';
      const input = document.getElementById('st-search-input');
      if (input) input.value = match.name;
    };
    item.innerHTML = `
      <div class="st-search-item-left">
        <div class="st-search-item-name">${match.icon || '🤖'} ${match.name}</div>
        <div class="st-search-item-div">${match.dept}</div>
      </div>
      <span class="st-search-item-badge">OPEN DOSSIER</span>
    `;
    resultsContainer.appendChild(item);
  });
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.st-top-right')) {
    const res = document.getElementById('st-search-results');
    if (res) res.style.display = 'none';
  }
});


