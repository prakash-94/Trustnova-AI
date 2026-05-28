/* ── trust.js — AI Trust dashboard, trend chart, source chunks ── */
const Trust = (() => {
  let initialized = false;
  let trendChart = null;
  let lastChatData = null;

  async function init() {
    if (initialized) return;
    initialized = true;
    await loadStats();
    await loadTrend();
  }

  // Called by banker.js after every chat response
  function updateFromChat(chatData) {
    lastChatData = chatData;

    const score = Math.round(chatData.ai_trust_score || 0);
    const tier  = chatData.trust_tier || '—';

    // Update gauge
    drawGauge('aiGaugeArc', 'aiGaugeValue', null, score, tier);
    const el = document.getElementById('aiGaugeValue');
    if (el) el.style.color = score >= 71 ? '#10b981' : score >= 41 ? '#f59e0b' : '#ef4444';

    // Tier badge
    const badge = document.getElementById('trustTierBadge');
    if (badge) {
      badge.textContent = tier;
      badge.className = `badge ${tier === 'Trusted' ? 'badge-green' : tier === 'Moderate' ? 'badge-amber' : 'badge-red'}`;
    }

    // Hide hint
    const hint = document.getElementById('trustHint');
    if (hint) hint.style.display = 'none';

    // Component bars
    renderTrustBars('aiTrustComponentBars', chatData.trust_components || {});

    // Source chunks
    renderSourceChunks(chatData.retrieved_chunks || [], chatData.sources || []);

    // Refresh trend
    loadTrend();
  }

  function renderSourceChunks(chunks, sources) {
    const el = document.getElementById('sourceChunksPanel');
    const badge = document.getElementById('chunkCount');
    if (!el) return;
    if (!chunks.length) {
      el.innerHTML = `<div class="empty-state"><div style="font-size:2rem">📄</div><p>Source chunks appear here after a chat query.</p></div>`;
      if (badge) badge.textContent = '0 chunks';
      return;
    }
    if (badge) badge.textContent = `${chunks.length} chunk${chunks.length > 1 ? 's' : ''}`;
    el.innerHTML = chunks.map((c, i) => {
      const src = sources[i] || {};
      return `<div class="chunk-item">
        <div>${String(c).slice(0, 280)}${c.length > 280 ? '…' : ''}</div>
        <div class="chunk-src">📎 ${src.source || src.doc_type || 'Source ' + (i+1)}</div>
      </div>`;
    }).join('');
  }

  async function loadTrend() {
    try {
      const d = await api.get('/trust/ai-history?limit=20');
      const history = (d.history || []).reverse();
      renderTrendChart(history);
    } catch { /* silent */ }
  }

  function renderTrendChart(history) {
    const ctx = document.getElementById('trustTrendChart');
    if (!ctx) return;
    if (trendChart) trendChart.destroy();

    const labels = history.map((_, i) => `#${i + 1}`);
    const scores = history.map(h => Math.round(h.final_score || 0));

    trendChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'AI Trust Score',
          data: scores,
          borderColor: '#6366f1',
          backgroundColor: 'rgba(99,102,241,.1)',
          fill: true,
          tension: 0.4,
          pointBackgroundColor: scores.map(s => s >= 71 ? '#10b981' : s >= 41 ? '#f59e0b' : '#ef4444'),
          pointRadius: 4,
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,.04)' }, ticks: { color: '#64748b', font: { size: 10 } } },
          y: {
            min: 0, max: 100,
            grid: { color: 'rgba(255,255,255,.04)' },
            ticks: { color: '#64748b', font: { size: 10 } },
          },
        },
      },
    });
  }

  async function loadStats() {
    const el = document.getElementById('feedbackStatsPanel');
    try {
      const d = await api.get('/feedback/report?days=30');
      const r = d.report || d;
      const total = r.total_feedback || 0;
      const overall = r.overall || {};

      if (!total) {
        el.innerHTML = `<div class="empty-state"><p>No feedback data yet.<br>Use the Banker Copilot to generate data.</p></div>`;
        return;
      }

      el.innerHTML = `
        <div class="stats-grid" style="grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px">
          <div class="stat-tile"><div class="stat-label">Total Feedback</div><div class="stat-val">${total}</div></div>
          <div class="stat-tile"><div class="stat-label">Approval Rate</div><div class="stat-val" style="color:var(--green)">${((overall.approval_rate||0)*100).toFixed(0)}%</div></div>
          <div class="stat-tile"><div class="stat-label">Rejection Rate</div><div class="stat-val" style="color:var(--red)">${((overall.rejection_rate||0)*100).toFixed(0)}%</div></div>
          <div class="stat-tile"><div class="stat-label">Edit Rate</div><div class="stat-val" style="color:var(--amber)">${((overall.edit_rate||0)*100).toFixed(0)}%</div></div>
        </div>
        ${renderModelTable(r.by_model || {})}`;
    } catch {
      el.innerHTML = `<div class="empty-state"><p>Stats unavailable.</p></div>`;
    }
  }

  function renderModelTable(byModel) {
    const entries = Object.entries(byModel);
    if (!entries.length) return '';
    return `<table class="data-table">
      <thead><tr><th>Model</th><th>Total</th><th>Approval</th><th>Rejection</th></tr></thead>
      <tbody>${entries.map(([m, s]) => `<tr>
        <td><span class="badge badge-purple">${m}</span></td>
        <td>${s.total || 0}</td>
        <td style="color:var(--green)">${((s.approval_rate||0)*100).toFixed(0)}%</td>
        <td style="color:var(--red)">${((s.rejection_rate||0)*100).toFixed(0)}%</td>
      </tr>`).join('')}</tbody>
    </table>`;
  }

  return { init, updateFromChat };
})();
