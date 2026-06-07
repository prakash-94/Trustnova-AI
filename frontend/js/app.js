/* ── app.js — Auth, shared utilities, tab routing, API client ── */
const API = window.location.origin;


// ── Auth helpers ───────────────────────────────────────────────
const Auth = {
  getToken()  { return sessionStorage.getItem('auth_token'); },
  getUser()   {
    try { return JSON.parse(sessionStorage.getItem('auth_user') || 'null'); }
    catch { return null; }
  },
  setSession(token, user) {
    sessionStorage.setItem('auth_token', token);
    sessionStorage.setItem('auth_user', JSON.stringify(user));
  },
  clear() {
    sessionStorage.removeItem('auth_token');
    sessionStorage.removeItem('auth_user');
  },
  redirectLogin() { window.location.href = '/login'; },
};


// ── API client (auth-aware) ────────────────────────────────────
const api = {
  _authHeaders() {
    const t = Auth.getToken();
    return t ? { Authorization: `Bearer ${t}` } : {};
  },
  _check401(r) {
    if (r.status === 401 || r.status === 403) {
      Auth.clear();
      Auth.redirectLogin();
      throw new Error('Session expired — redirecting to login.');
    }
  },
  async get(path) {
    const r = await fetch(`${API}${path}`, { headers: this._authHeaders() });
    this._check401(r);
    if (!r.ok) throw new Error(`HTTP ${r.status} from GET ${path}`);
    return r.json();
  },
  async post(path, body) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 120000);
    try {
      const r = await fetch(`${API}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...this._authHeaders() },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      this._check401(r);
      if (!r.ok) {
        const txt = await r.text().catch(() => '');
        throw new Error(`HTTP ${r.status} — ${txt.slice(0, 200) || r.statusText}`);
      }
      return r.json();
    } catch (e) {
      clearTimeout(timer);
      if (e.name === 'AbortError') throw new Error('Request timed out after 120s. The AI model may be slow — try again.');
      if (e.message === 'Failed to fetch') throw new Error(`Network error: cannot reach ${API}${path}. Check backend is running.`);
      throw e;
    }
  },
  async upload(path, formData) {
    const r = await fetch(`${API}${path}`, {
      method: 'POST',
      headers: this._authHeaders(),  // No Content-Type header — browser sets multipart boundary
      body: formData,
    });
    this._check401(r);
    if (!r.ok) throw new Error(`HTTP ${r.status} upload error`);
    return r.json();
  },
};


// ── Dashboard boot ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  // Redirect to login if no token
  if (!Auth.getToken()) {
    Auth.redirectLogin();
    return;
  }

  // Validate token and populate user UI
  try {
    const me = await api.get('/auth/me');
    Auth.setSession(Auth.getToken(), me);
    renderUserBar(me);
    applyRoleVisibility(me.permissions || []);
  } catch {
    Auth.clear();
    Auth.redirectLogin();
    return;
  }

  // Nav click
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Logout button
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
      try { await api.post('/auth/logout', {}); } catch { /* ignore */ }
      Auth.clear();
      Auth.redirectLogin();
    });
  }

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


function renderUserBar(user) {
  const nameEl = document.getElementById('topbarUserName');
  const roleEl = document.getElementById('topbarUserRole');
  if (nameEl) nameEl.textContent = user.full_name || user.username;
  if (roleEl) {
    roleEl.textContent = user.role_label || user.role;
    const roleColors = {
      admin: '#a78bfa',
      banker: '#60a5fa',
      fraud_analyst: '#f87171',
      compliance_officer: '#34d399',
    };
    roleEl.style.color = roleColors[user.role] || '#94a3b8';
  }
}


// Role-based nav tab hiding
function applyRoleVisibility(permissions) {
  const navPermMap = {
    'nav-banker': 'chat',
    'nav-fraud':  'fraud',
    'nav-trust':  'trust',
    'nav-docs':   'documents',
  };
  Object.entries(navPermMap).forEach(([navId, perm]) => {
    const el = document.getElementById(navId);
    if (!el) return;
    const allowed = permissions.some(p => p === perm || p.split(':')[0] === perm);
    if (!allowed) {
      el.style.display = 'none';
      // If this was the active tab, switch to first visible tab
      if (el.classList.contains('active')) {
        const first = document.querySelector('.nav-item:not([style*="none"])');
        if (first) first.click();
      }
    }
  });
}


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


const pageMeta = {
  banker: { title: 'Banker Copilot', sub: 'Search a customer and ask the AI copilot anything.' },
  fraud:  { title: 'Fraud Monitor', sub: 'Real-time fraud alerts and transaction risk scoring.' },
  trust:  { title: 'AI Trust Dashboard', sub: 'Monitor AI response quality and trust components.' },
  docs:   { title: 'Document Intelligence', sub: 'Upload documents and query banking policies.' },
};


async function checkHealth() {
  const dot = document.getElementById('statusDot');
  const label = document.getElementById('statusLabel');
  try {
    const d = await fetch(`${API}/health`).then(r => r.json());
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


// ── Gauge ──────────────────────────────────────────────────────
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


// ── Trust component bars ───────────────────────────────────────
function renderTrustBars(containerId, components) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!components || !Object.keys(components).length) { el.innerHTML = ''; return; }
  const labels = {
    retrieval_confidence: 'Retrieval Confidence',
    hallucination_probability: 'Hallucination Risk',
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


// ── Badges / helpers ───────────────────────────────────────────
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
