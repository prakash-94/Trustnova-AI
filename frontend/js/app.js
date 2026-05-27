/* ============================================================
   App Controller — Tab routing, API client, shared utilities
   ============================================================ */

const API = window.location.origin;

// --- API Client ---
const api = {
  async get(path) {
    const res = await fetch(`${API}${path}`);
    return res.json();
  },
  async post(path, body) {
    const res = await fetch(`${API}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res.json();
  },
  async upload(path, formData) {
    const res = await fetch(`${API}${path}`, { method: 'POST', body: formData });
    return res.json();
  },
};

// --- Tab Routing ---
document.addEventListener('DOMContentLoaded', () => {
  const tabs = document.querySelectorAll('.tab-btn');
  const panels = document.querySelectorAll('.tab-panel');

  tabs.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      tabs.forEach(t => t.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${target}`).classList.add('active');

      // Trigger load on first visit
      if (target === 'fraud') Fraud.init();
      if (target === 'trust') Trust.init();
      if (target === 'docs') Docs.init();
    });
  });

  // Health check
  checkHealth();
});

async function checkHealth() {
  try {
    const data = await api.get('/health');
    if (data.status === 'ok') {
      document.getElementById('headerStatus').textContent = 'System Online';
    }
  } catch {
    document.getElementById('headerStatus').textContent = 'Offline';
    document.querySelector('.status-dot').style.background = '#ef4444';
  }
}

// --- Gauge Drawing Utility ---
function drawGauge(arcId, valueId, tierId, score, tier) {
  const maxDash = 188;
  const dash = (score / 100) * maxDash;
  const arc = document.getElementById(arcId);
  if (arc) {
    arc.style.transition = 'stroke-dasharray 1s ease';
    arc.setAttribute('stroke-dasharray', `${dash} ${maxDash}`);
  }
  const valEl = document.getElementById(valueId);
  if (valEl) {
    animateNumber(valEl, score);
    valEl.style.color = score >= 71 ? '#10b981' : score >= 41 ? '#f59e0b' : '#ef4444';
  }
  const tierEl = document.getElementById(tierId);
  if (tierEl) tierEl.textContent = tier || '';
}

function animateNumber(el, target) {
  let current = 0;
  const step = Math.ceil(target / 30);
  const timer = setInterval(() => {
    current += step;
    if (current >= target) { current = target; clearInterval(timer); }
    el.textContent = Math.round(current);
  }, 20);
}

// --- Badge Utility ---
function riskBadge(level) {
  const map = {
    'Low': 'badge-green', 'Medium': 'badge-amber', 'High': 'badge-red',
    'Trusted': 'badge-green', 'Moderate': 'badge-amber', 'High Risk': 'badge-red',
  };
  return `<span class="badge ${map[level] || 'badge-blue'}">${level}</span>`;
}

function formatCurrency(val) {
  return '$' + Number(val || 0).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}
