/* ── fraud.js — Fraud monitor, alert feed, chart, checker ── */
const Fraud = (() => {
  let initialized = false;
  let riskChart = null;
  let alertsData = [];

  async function init() {
    if (initialized) return;
    initialized = true;
    await refresh();
  }

  async function refresh() {
    const feed = document.getElementById('fraudAlertFeed');
    feed.innerHTML = `<div class="loading-state"><div class="spinner"></div><span>Loading alerts…</span></div>`;
    try {
      const d = await api.get('/fraud/alerts?limit=50');
      alertsData = d.alerts || [];
      renderFeed(alertsData);
      renderKpis(alertsData);
      renderChart(alertsData);
      updateBadge(alertsData);
    } catch (e) {
      feed.innerHTML = `<div class="loading-state" style="color:var(--red)">⚠️ Failed to load alerts</div>`;
    }
  }

  function updateBadge(alerts) {
    const high = alerts.filter(a => (a.risk_score || 0) >= 0.7).length;
    const badge = document.getElementById('fraudBadgeCount');
    if (badge) badge.textContent = high || '0';
  }

  function renderKpis(alerts) {
    const high = alerts.filter(a => (a.risk_score || 0) >= 0.7).length;
    const med  = alerts.filter(a => (a.risk_score || 0) >= 0.3 && (a.risk_score || 0) < 0.7).length;
    const low  = alerts.filter(a => (a.risk_score || 0) < 0.3).length;
    const avg  = alerts.length ? (alerts.reduce((s, a) => s + (a.risk_score || 0), 0) / alerts.length) : 0;

    document.getElementById('kpiHighCount').textContent = high;
    document.getElementById('kpiMedCount').textContent = med;
    document.getElementById('kpiLowCount').textContent = low;
    document.getElementById('kpiAvgRisk').textContent = (avg * 100).toFixed(0) + '%';
  }

  function renderFeed(alerts) {
    const el = document.getElementById('fraudAlertFeed');
    if (!alerts.length) {
      el.innerHTML = `<div class="empty-state"><div style="font-size:2rem">🛡️</div><p>No fraud alerts found.</p></div>`;
      return;
    }
    el.innerHTML = alerts.slice(0, 30).map((a, i) => {
      const score = a.risk_score || 0;
      const tier = score >= 0.7 ? 'High' : score >= 0.3 ? 'Medium' : 'Low';
      const col  = score >= 0.7 ? '#ef4444' : score >= 0.3 ? '#f59e0b' : '#10b981';
      const pct  = Math.round(score * 100);
      return `<div class="alert-item" onclick="Fraud.openModal(${i})">
        <div class="alert-bar ${tier.toLowerCase()}"></div>
        <div class="alert-info">
          <div class="alert-title">${a.transaction_id || a.alert_id || 'Alert #' + (i+1)}</div>
          <div class="alert-meta">${a.customer_id || '—'} · ${fmtDate(a.timestamp || a.created_at)}</div>
        </div>
        <div>
          <span class="badge ${tier === 'High' ? 'badge-red' : tier === 'Medium' ? 'badge-amber' : 'badge-green'}">${tier}</span>
        </div>
        <div class="alert-score" style="color:${col}">${pct}%</div>
      </div>`;
    }).join('');
  }

  function renderChart(alerts) {
    const ctx = document.getElementById('riskDistChart');
    if (!ctx) return;
    if (riskChart) riskChart.destroy();

    const buckets = [0, 0, 0, 0, 0]; // 0-20, 20-40, 40-60, 60-80, 80-100
    alerts.forEach(a => {
      const s = Math.min(1, Math.max(0, a.risk_score || 0));
      buckets[Math.min(4, Math.floor(s * 5))]++;
    });

    riskChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['0–20%', '20–40%', '40–60%', '60–80%', '80–100%'],
        datasets: [{
          label: 'Transactions',
          data: buckets,
          backgroundColor: ['#10b981','#22d3ee','#f59e0b','#f97316','#ef4444'],
          borderRadius: 6, borderSkipped: false,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,.05)' }, ticks: { color: '#94a3b8', font: { size: 11 } } },
          y: { grid: { color: 'rgba(255,255,255,.05)' }, ticks: { color: '#94a3b8', font: { size: 11 } } },
        },
      },
    });
  }

  function openModal(idx) {
    const a = alertsData[idx];
    if (!a) return;
    const score = a.risk_score || 0;
    const tier = score >= 0.7 ? 'High' : score >= 0.3 ? 'Medium' : 'Low';
    const body = document.getElementById('fraudModalBody');
    body.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
        <div class="stat-tile"><div class="stat-label">Transaction ID</div><div class="stat-val" style="font-size:.85rem">${a.transaction_id || a.alert_id || '—'}</div></div>
        <div class="stat-tile"><div class="stat-label">Customer</div><div class="stat-val" style="font-size:.85rem">${a.customer_id || '—'}</div></div>
        <div class="stat-tile"><div class="stat-label">Risk Score</div><div class="stat-val" style="color:${score>=.7?'#ef4444':score>=.3?'#f59e0b':'#10b981'}">${Math.round(score*100)}%</div></div>
        <div class="stat-tile"><div class="stat-label">Risk Tier</div><div class="stat-val">${riskBadge(tier)}</div></div>
        <div class="stat-tile"><div class="stat-label">Status</div><div class="stat-val">${a.status || '—'}</div></div>
        <div class="stat-tile"><div class="stat-label">Timestamp</div><div class="stat-val" style="font-size:.8rem">${fmtDate(a.timestamp || a.created_at)}</div></div>
      </div>
      ${a.reason || a.explanation ? `<div class="chunk-item" style="border-left:3px solid var(--amber)">
        <strong style="font-size:.78rem;color:var(--amber)">⚠️ Risk Explanation</strong>
        <div style="margin-top:8px;color:var(--t2)">${a.reason || a.explanation}</div>
      </div>` : ''}
      <div style="margin-top:14px;display:flex;gap:8px">
        <button class="btn btn-ghost btn-sm" onclick="Fraud.closeModal()">Close</button>
        <button class="btn btn-sm" style="background:var(--grad-r);color:#fff" onclick="Fraud.closeModal()">Override — Mark Safe</button>
      </div>`;
    document.getElementById('fraudModal').classList.remove('hidden');
  }

  function closeModal() {
    document.getElementById('fraudModal').classList.add('hidden');
  }

  async function checkTransaction() {
    const resultEl = document.getElementById('fraudCheckResult');
    resultEl.innerHTML = `<div class="loading-state"><div class="spinner"></div><span>Checking…</span></div>`;

    const body = {
      amount:           parseFloat(document.getElementById('fraudAmount').value) || 1000,
      hour:             parseInt(document.getElementById('fraudHour').value) || 12,
      geo_mismatch:     parseInt(document.getElementById('fraudGeo').value) || 0,
      device_new:       parseInt(document.getElementById('fraudDevice').value) || 0,
      credit_score:     parseInt(document.getElementById('fraudCredit').value) || 650,
      merchant_risk:    parseFloat(document.getElementById('fraudMerchant').value) || 0.3,
      is_weekend:       new Date().getDay() % 6 === 0 ? 1 : 0,
      amount_zscore:    2.0,
      velocity_30m:     1,
      account_age_days: 365,
      use_ensemble:     true,
    };

    try {
      const d = await api.post('/fraud/check', body);
      const prob = Math.round((d.fraud_probability || 0) * 100);
      const tier = d.risk_tier || '—';
      const col  = tier === 'High' ? '#ef4444' : tier === 'Medium' ? '#f59e0b' : '#10b981';

      const factors = (d.top_risk_factors || []).slice(0, 3).map(f =>
        `<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:.78rem;color:var(--t2)">
          <strong style="color:var(--t1)">${f.feature}</strong>: value ${Number(f.value).toFixed(2)}, importance ${Number(f.importance).toFixed(3)}
        </div>`).join('');

      resultEl.innerHTML = `
        <div style="display:flex;align-items:center;gap:14px;margin-bottom:12px">
          <div style="font-size:2rem;font-weight:900;color:${col}">${prob}%</div>
          <div>${riskBadge(tier)}<div style="font-size:.72rem;color:var(--t2);margin-top:4px">Models: ${(d.models_used||[]).join('+')}</div></div>
        </div>
        ${factors ? `<div style="margin-bottom:10px">${factors}</div>` : ''}
        ${d.explanation ? `<div class="chunk-item" style="font-size:.78rem;color:var(--t2)">${d.explanation}</div>` : ''}`;
    } catch (e) {
      resultEl.innerHTML = `<span style="color:var(--red)">⚠️ Check failed: ${e.message}</span>`;
    }
  }

  return { init, refresh, openModal, closeModal, checkTransaction };
})();
