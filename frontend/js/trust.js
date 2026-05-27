/* ============================================================
   AI Trust Dashboard — Gauge, breakdown, source chunks, trend
   ============================================================ */

const Trust = (() => {
  let initialized = false;
  let lastChatData = null;

  function init() {
    if (initialized) return;
    initialized = true;
    loadHistory();
    loadFeedbackStats();
  }

  // Called from Banker chat after each response
  function updateFromChat(data) {
    lastChatData = data;
    const score = Math.round(data.ai_trust_score || 0);
    const tier = data.trust_tier || (score >= 71 ? 'Trusted' : score >= 41 ? 'Moderate' : 'High Risk');

    drawGauge('aiGaugeArc', 'aiGaugeValue', 'aiGaugeTier', score, tier);
    renderBreakdown(data.trust_components);
    renderSourceChunks(data.retrieved_chunks);
  }

  function renderBreakdown(components) {
    const container = document.getElementById('trustBreakdown');
    if (!components || Object.keys(components).length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No trust data yet.</p></div>';
      return;
    }

    const labels = {
      retrieval_confidence: 'Retrieval Confidence',
      hallucination_risk: 'Hallucination Risk',
      model_agreement: 'Model Agreement',
      citation_quality: 'Citation Quality',
      source_coverage: 'Source Coverage',
    };

    container.innerHTML = Object.entries(components).map(([key, val]) => {
      const pct = Math.round(val * 100);
      const color = pct >= 70 ? '#10b981' : pct >= 40 ? '#f59e0b' : '#ef4444';
      // For hallucination_risk, lower is better
      const displayColor = key === 'hallucination_risk'
        ? (pct <= 30 ? '#10b981' : pct <= 60 ? '#f59e0b' : '#ef4444')
        : color;
      return `
        <div class="trust-metric">
          <div class="trust-metric-label">${labels[key] || key}</div>
          <div class="trust-metric-bar">
            <div class="trust-metric-fill" style="width:${pct}%;background:${displayColor};"></div>
          </div>
          <div class="trust-metric-value" style="color:${displayColor}">${pct}%</div>
        </div>`;
    }).join('');
  }

  function renderSourceChunks(chunks) {
    const container = document.getElementById('sourceChunksPanel');
    if (!chunks || chunks.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No source chunks retrieved.</p></div>';
      return;
    }
    container.innerHTML = chunks.slice(0, 5).map((c, i) => `
      <div class="note-item" style="border-left-color:var(--accent-cyan);">
        <div style="font-size:0.72rem;color:var(--accent-cyan);margin-bottom:4px;">Chunk ${i + 1}</div>
        ${c.length > 300 ? c.slice(0, 300) + '...' : c}
      </div>
    `).join('');
  }

  async function loadHistory() {
    try {
      const data = await api.get('/trust/ai-history?limit=30');
      if (data.status === 'ok' && data.history && data.history.length > 0) {
        renderTrendChart(data.history);
        // Show the latest score
        const latest = data.history[0];
        if (latest && latest.final_score !== undefined) {
          const score = Math.round(latest.final_score);
          const tier = score >= 71 ? 'Trusted' : score >= 41 ? 'Moderate' : 'High Risk';
          drawGauge('aiGaugeArc', 'aiGaugeValue', 'aiGaugeTier', score, tier);
          renderBreakdown(latest.components || {});
        }
      }
    } catch { /* ignore */ }
  }

  function renderTrendChart(history) {
    const canvas = document.getElementById('trustTrendChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.parentElement.clientWidth;
    canvas.width = w; canvas.height = 200;
    ctx.clearRect(0, 0, w, 200);

    const scores = history.map(h => h.final_score || 0).reverse();
    const len = scores.length;
    if (len < 2) return;

    const padL = 40, padR = 20, padT = 10, padB = 30;
    const chartW = w - padL - padR;
    const chartH = 200 - padT - padB;

    // Grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padT + (i / 4) * chartH;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
      ctx.fillStyle = '#64748b';
      ctx.font = '10px Inter';
      ctx.textAlign = 'right';
      ctx.fillText(Math.round(100 - (i / 4) * 100), padL - 6, y + 4);
    }

    // Line
    const grad = ctx.createLinearGradient(padL, 0, w - padR, 0);
    grad.addColorStop(0, '#6366f1');
    grad.addColorStop(1, '#22d3ee');
    ctx.strokeStyle = grad;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    scores.forEach((s, i) => {
      const x = padL + (i / (len - 1)) * chartW;
      const y = padT + (1 - s / 100) * chartH;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Fill area
    const areaGrad = ctx.createLinearGradient(0, padT, 0, padT + chartH);
    areaGrad.addColorStop(0, 'rgba(99, 102, 241, 0.15)');
    areaGrad.addColorStop(1, 'rgba(99, 102, 241, 0)');
    ctx.lineTo(padL + chartW, padT + chartH);
    ctx.lineTo(padL, padT + chartH);
    ctx.closePath();
    ctx.fillStyle = areaGrad;
    ctx.fill();

    // Dots
    scores.forEach((s, i) => {
      const x = padL + (i / (len - 1)) * chartW;
      const y = padT + (1 - s / 100) * chartH;
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fillStyle = '#6366f1';
      ctx.fill();
    });
  }

  async function loadFeedbackStats() {
    try {
      const data = await api.get('/feedback/stats');
      const container = document.getElementById('feedbackStatsPanel');
      if (data.status === 'ok' && data.stats) {
        const s = data.stats;
        container.innerHTML = `
          <div class="profile-stats">
            <div class="stat-item"><div class="stat-label">Total Feedback</div><div class="stat-value">${s.total_feedback || 0}</div></div>
            <div class="stat-item"><div class="stat-label">Agreement Rate</div><div class="stat-value">${s.agreement_rate ? (s.agreement_rate * 100).toFixed(0) + '%' : '—'}</div></div>
            <div class="stat-item"><div class="stat-label">False Positives</div><div class="stat-value">${s.model_false_positives || 0}</div></div>
            <div class="stat-item"><div class="stat-label">False Negatives</div><div class="stat-value">${s.model_false_negatives || 0}</div></div>
          </div>`;
      } else {
        container.innerHTML = '<div class="empty-state"><p>No feedback data yet.</p></div>';
      }
    } catch {
      document.getElementById('feedbackStatsPanel').innerHTML = '<div class="empty-state"><p>Could not load stats.</p></div>';
    }
  }

  return { init, updateFromChat };
})();
