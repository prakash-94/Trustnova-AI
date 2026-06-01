/* ── app.js — Shared utilities, tab routing, API client ── */
const API = window.location.origin;

const api = {
  async get(path) {
    const r = await fetch(`${API}${path}`);
    if (!r.ok) throw new Error(`HTTP ${r.status} from GET ${path}`);
    return r.json();
  },
  async post(path, body) {
    // 120-second timeout for GPT-4 responses
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 120000);
    try {
      const r = await fetch(`${API}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      if (!r.ok) {
        const txt = await r.text().catch(() => '');
        throw new Error(`HTTP ${r.status} — ${txt.slice(0,200) || r.statusText}`);
      }
      return r.json();
    } catch (e) {
      clearTimeout(timer);
      if (e.name === 'AbortError') throw new Error('Request timed out after 120s. The AI model may be slow — try again.');
      // "Failed to fetch" = network-level error. Include URL for debugging.
      if (e.message === 'Failed to fetch') throw new Error(`Network error: cannot reach ${API}${path}. Check backend is running.`);
      throw e;
    }
  },
  async upload(path, formData) {
    const r = await fetch(`${API}${path}`, { method: 'POST', body: formData });
    if (!r.ok) throw new Error(`HTTP ${r.status} upload error`);
    return r.json();
  },
};


// ── Tab routing ────────────────────────────────────────────
const pageMeta = {
  banker: { title: 'Banker Copilot', sub: 'Search a customer and ask the AI copilot anything.' },
  fraud:  { title: 'Fraud Monitor', sub: 'Real-time fraud alerts and transaction risk scoring.' },
  trust:  { title: 'AI Trust Dashboard', sub: 'Monitor AI response quality and trust components.' },
  docs:   { title: 'Document Intelligence', sub: 'Upload documents and query banking policies.' },
};

document.addEventListener('DOMContentLoaded', () => {
  // Nav click
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Chat suggestions
  document.querySelectorAll('.chat-suggestions .chip').forEach(c => {
    c.addEventListener('click', () => {
      const q = c.dataset.q;
      document.getElementById('chatInput').value = q;
      Banker.sendMessage();
    });
  });

  // Policy query suggestions
  document.querySelectorAll('.policy-suggestions .chip').forEach(c => {
    c.addEventListener('click', () => {
      document.getElementById('policyQuery').value = c.dataset.pq;
      Docs.queryPolicy();
    });
  });

  // Clock
  updateClock();
  setInterval(updateClock, 1000);

  // Health check
  checkHealth();
});

function switchTab(tab) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  const navEl = document.getElementById(`nav-${tab}`);
  if (navEl) navEl.classList.add('active');
  const panelEl = document.getElementById(`tab-${tab}`);
  if (panelEl) panelEl.classList.add('active');

  const m = pageMeta[tab] || {};
  document.getElementById('pageTitle').textContent = m.title || tab;
  document.getElementById('pageSub').textContent = m.sub || '';

  if (tab === 'fraud') Fraud.init();
  if (tab === 'trust') Trust.init();
  if (tab === 'docs') Docs.init();
}

async function checkHealth() {
  const dot = document.getElementById('statusDot');
  const label = document.getElementById('statusLabel');
  try {
    const d = await api.get('/health');
    if (d.status === 'ok') {
      dot.className = 'status-indicator online';
      label.textContent = 'System Online';
    }
  } catch {
    dot.className = 'status-indicator error';
    label.textContent = 'Offline';
  }
}

function updateClock() {
  const el = document.getElementById('clockEl');
  if (el) el.textContent = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

// ── Gauge ──────────────────────────────────────────────────
function drawGauge(arcId, scoreId, tierId, score, tier) {
  const maxDash = 251;
  const dash = (Math.min(100, Math.max(0, score)) / 100) * maxDash;
  const arc = document.getElementById(arcId);
  if (arc) {
    setTimeout(() => arc.setAttribute('stroke-dasharray', `${dash} ${maxDash}`), 50);
    arc.style.transition = 'stroke-dasharray 1s ease';
  }
  const valEl = document.getElementById(scoreId);
  if (valEl) {
    animCount(valEl, score);
    valEl.style.color = score >= 71 ? '#10b981' : score >= 41 ? '#f59e0b' : '#ef4444';
  }
  const tierEl = document.getElementById(tierId);
  if (tierEl) tierEl.textContent = tier || '';
}

function animCount(el, target) {
  let cur = 0;
  const step = Math.max(1, Math.ceil(target / 40));
  const t = setInterval(() => {
    cur = Math.min(cur + step, target);
    el.textContent = Math.round(cur);
    if (cur >= target) clearInterval(t);
  }, 18);
}

// ── Trust component bars ───────────────────────────────────
function renderTrustBars(containerId, components) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!components || !Object.keys(components).length) { el.innerHTML = ''; return; }
  const labels = {
    retrieval_confidence: 'Retrieval Confidence',
    hallucination_prob: 'Hallucination Risk',
    model_agreement: 'Model Agreement',
    citation_quality: 'Citation Quality',
    prompt_reliability: 'Prompt Reliability',
  };
  el.innerHTML = Object.entries(components).map(([k, v]) => {
    const pct = Math.round(v * 100);
    const col = pct >= 70 ? '#10b981' : pct >= 40 ? '#f59e0b' : '#ef4444';
    return `<div class="trust-bar-row">
      <span class="trust-bar-label">${labels[k] || k}</span>
      <div class="trust-bar-track"><div class="trust-bar-fill" style="width:${pct}%;background:${col}"></div></div>
      <span class="trust-bar-val">${pct}%</span>
    </div>`;
  }).join('');
}

// ── Badges / helpers ───────────────────────────────────────
function riskBadge(level) {
  const map = { Low: 'badge-green', Medium: 'badge-amber', High: 'badge-red', Trusted: 'badge-green', Moderate: 'badge-amber', 'High Risk': 'badge-red' };
  return `<span class="badge ${map[level] || 'badge-blue'}">${level}</span>`;
}

function fmt$(v) {
  return '$' + Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function fmtDate(s) {
  if (!s) return '—';
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
