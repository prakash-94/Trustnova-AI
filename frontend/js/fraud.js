/* ============================================================
   Fraud Monitor — Alert feed, risk chart, detail modal, override
   ============================================================ */

const Fraud = (() => {
  let initialized = false;
  let alerts = [];

  function init() {
    if (initialized) return;
    initialized = true;
    refresh();
  }

  async function refresh() {
    try {
      const data = await api.get('/fraud/alerts?limit=20');
      if (data.status === 'ok' && data.alerts) {
        alerts = data.alerts;
        renderAlerts(data.alerts);
        renderChart(data.alerts);
      } else {
        renderAlerts([]);
      }
    } catch {
      renderAlerts([]);
    }
  }

  function renderAlerts(list) {
    const container = document.getElementById('fraudAlertList');
    if (!list || list.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No fraud alerts found.</p></div>';
      return;
    }
    container.innerHTML = list.map((a, i) => {
      const score = parseFloat(a.risk_score || a.fraud_probability || 0);
      const tier = score >= 0.7 ? 'High' : score >= 0.3 ? 'Medium' : 'Low';
      const color = tier === 'High' ? '#ef4444' : tier === 'Medium' ? '#f59e0b' : '#10b981';
      return `
        <div class="alert-item" onclick="Fraud.showDetail(${i})">
          <div class="alert-risk-bar" style="background:${color}"></div>
          <div class="alert-info">
            <div class="alert-title">${a.customer_id || 'Unknown'} — ${formatCurrency(a.amount || 0)}</div>
            <div class="alert-meta">${a.reason || a.explanation || tier + ' Risk'} | ${(a.timestamp || '').slice(0, 10)}</div>
          </div>
          <div class="alert-score" style="color:${color}">${(score * 100).toFixed(0)}%</div>
        </div>`;
    }).join('');
  }

  function renderChart(list) {
    const canvas = document.getElementById('riskChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.parentElement.clientWidth;
    canvas.width = w; canvas.height = 200;
    ctx.clearRect(0, 0, w, 200);

    // Build histogram
    const buckets = Array(10).fill(0);
    (list || []).forEach(a => {
      const score = parseFloat(a.risk_score || a.fraud_probability || 0);
      const idx = Math.min(9, Math.floor(score * 10));
      buckets[idx]++;
    });

    const maxVal = Math.max(...buckets, 1);
    const barW = (w - 60) / 10;
    const barArea = 160;

    // Bars
    buckets.forEach((val, i) => {
      const h = (val / maxVal) * barArea;
      const x = 40 + i * barW;
      const y = 180 - h;
      const pct = (i + 0.5) / 10;
      const r = Math.round(239 * pct + 16 * (1 - pct));
      const g = Math.round(68 * pct + 185 * (1 - pct));
      const b = Math.round(68 * pct + 129 * (1 - pct));
      ctx.fillStyle = `rgba(${r},${g},${b},0.7)`;
      ctx.beginPath();
      ctx.roundRect(x + 2, y, barW - 4, h, 4);
      ctx.fill();
    });

    // Labels
    ctx.fillStyle = '#64748b';
    ctx.font = '10px Inter, sans-serif';
    ctx.textAlign = 'center';
    for (let i = 0; i <= 10; i++) {
      ctx.fillText(`${i * 10}%`, 40 + i * barW, 196);
    }
    ctx.textAlign = 'right';
    for (let i = 0; i <= 4; i++) {
      const val = Math.round(maxVal * i / 4);
      ctx.fillText(val, 35, 180 - (i / 4) * barArea + 4);
    }
  }

  function showDetail(index) {
    const a = alerts[index];
    if (!a) return;

    const score = parseFloat(a.risk_score || a.fraud_probability || 0);
    const tier = score >= 0.7 ? 'High' : score >= 0.3 ? 'Medium' : 'Low';

    document.getElementById('fraudModalBody').innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
        <div class="alert-score" style="font-size:2rem;color:${tier === 'High' ? '#ef4444' : tier === 'Medium' ? '#f59e0b' : '#10b981'}">
          ${(score * 100).toFixed(1)}%
        </div>
        <div>
          <div style="font-size:1.1rem;font-weight:700;">Fraud Risk: ${riskBadge(tier)}</div>
          <div style="color:var(--text-secondary);font-size:0.8rem;">Customer: ${a.customer_id || '—'}</div>
        </div>
      </div>
      <div class="profile-stats" style="margin-bottom:16px;">
        <div class="stat-item"><div class="stat-label">Amount</div><div class="stat-value">${formatCurrency(a.amount)}</div></div>
        <div class="stat-item"><div class="stat-label">Timestamp</div><div class="stat-value" style="font-size:0.85rem;">${(a.timestamp || '—').slice(0, 19)}</div></div>
        <div class="stat-item"><div class="stat-label">Model</div><div class="stat-value">${a.model_used || 'XGBoost'}</div></div>
        <div class="stat-item"><div class="stat-label">Status</div><div class="stat-value">${a.status || 'Pending'}</div></div>
      </div>
      ${a.explanation ? `<div class="glass-card" style="margin-bottom:16px;"><div class="card-header"><div class="card-title">AI Explanation</div></div><div class="card-body" style="font-size:0.85rem;line-height:1.6;">${a.explanation}</div></div>` : ''}
      <div style="display:flex;gap:8px;">
        <button class="btn btn-success" onclick="Fraud.override(${index}, 'approve')">&#x2705; Approve (Not Fraud)</button>
        <button class="btn btn-danger" onclick="Fraud.override(${index}, 'reject')">&#x26A0; Confirm Fraud</button>
      </div>
      <div id="overrideResult" style="margin-top:12px;"></div>
    `;

    document.getElementById('fraudModal').classList.remove('hidden');
  }

  function closeModal() {
    document.getElementById('fraudModal').classList.add('hidden');
  }

  async function override(index, type) {
    const a = alerts[index];
    try {
      const data = await api.post('/feedback', {
        session_id: 'fraud_monitor',
        response_id: a.transaction_id || `fraud_${index}`,
        feedback_type: type,
        prompt: `Fraud check for ${a.customer_id}`,
        model_used: a.model_used || 'XGBoost',
        trust_score: parseFloat(a.risk_score || 0) * 100,
      });
      document.getElementById('overrideResult').innerHTML = `
        <div class="badge badge-green" style="font-size:0.8rem;padding:6px 12px;">
          Feedback submitted: ${type}
        </div>`;
    } catch (err) {
      document.getElementById('overrideResult').innerHTML = `<span style="color:#ef4444;">Error: ${err.message}</span>`;
    }
  }

  async function checkTransaction() {
    const amount = parseFloat(document.getElementById('fraudAmount').value) || 5000;
    const hour = parseInt(document.getElementById('fraudHour').value) || 2;
    const geo = parseInt(document.getElementById('fraudGeo').value) || 0;
    const device = parseInt(document.getElementById('fraudDevice').value) || 0;

    document.getElementById('fraudCheckResult').innerHTML = '<div class="spinner"></div>';

    try {
      const data = await api.post('/fraud/check', {
        amount, hour, geo_mismatch: geo, device_new: device,
        use_ensemble: true,
      });

      if (data.status === 'ok') {
        const prob = data.fraud_probability || 0;
        const tier = data.risk_tier || 'Low';
        const color = tier === 'High' ? '#ef4444' : tier === 'Medium' ? '#f59e0b' : '#10b981';
        let html = `
          <div style="display:flex;align-items:center;gap:12px;">
            <div style="font-size:1.5rem;font-weight:800;color:${color};">${(prob * 100).toFixed(1)}%</div>
            ${riskBadge(tier)}
            <span style="color:var(--text-secondary);font-size:0.8rem;">${data.models_used ? data.models_used.join(' + ') : ''} | ${data.latency_ms}ms</span>
          </div>`;
        if (data.explanation) {
          html += `<div style="margin-top:8px;font-size:0.82rem;color:var(--text-secondary);line-height:1.5;">${data.explanation}</div>`;
        }
        document.getElementById('fraudCheckResult').innerHTML = html;
      } else {
        document.getElementById('fraudCheckResult').innerHTML = `<span style="color:#ef4444;">${data.error || 'Error'}</span>`;
      }
    } catch (err) {
      document.getElementById('fraudCheckResult').innerHTML = `<span style="color:#ef4444;">Error: ${err.message}</span>`;
    }
  }

  return { init, refresh, showDetail, closeModal, override, checkTransaction };
})();
