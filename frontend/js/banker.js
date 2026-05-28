/* ── banker.js — Customer search, profile, chat, notes ── */
const Banker = (() => {
  let currentCustomerId = null;
  let sessionId = null;
  let searchTimer = null;

  // ── Customer Search ──────────────────────────────────────
  function initSearch() {
    const input = document.getElementById('customerSearch');
    const results = document.getElementById('searchResults');

    input.addEventListener('input', () => {
      clearTimeout(searchTimer);
      const q = input.value.trim();
      if (q.length < 2) { results.innerHTML = ''; results.style.display = 'none'; return; }
      searchTimer = setTimeout(() => doSearch(q), 300);
    });

    document.addEventListener('click', e => {
      if (!e.target.closest('#customerSearch') && !e.target.closest('#searchResults')) {
        results.innerHTML = ''; results.style.display = 'none';
      }
    });

    document.getElementById('chatSend').addEventListener('click', sendMessage);
    document.getElementById('chatInput').addEventListener('keydown', e => {
      if (e.key === 'Enter') sendMessage();
    });
    document.getElementById('clearChatBtn').addEventListener('click', clearChat);
  }

  async function doSearch(q) {
    const results = document.getElementById('searchResults');
    results.style.display = 'block';
    results.innerHTML = `<div class="loading-state" style="padding:12px"><div class="spinner"></div></div>`;
    try {
      const d = await api.get(`/customer/search?q=${encodeURIComponent(q)}&limit=6`);
      if (!d.results || !d.results.length) {
        results.innerHTML = `<div class="search-result-item" style="color:var(--t3)">No customers found</div>`;
        return;
      }
      results.innerHTML = d.results.map(c => `
        <div class="search-result-item" onclick="Banker.selectCustomer('${c.customer_id}')">
          <div class="search-result-name">${c.name}</div>
          <div class="search-result-meta">${c.customer_id} · ${c.account_type || ''} · ${fmt$(c.balance)}</div>
        </div>`).join('');
    } catch {
      results.innerHTML = `<div class="search-result-item" style="color:var(--red)">Search failed</div>`;
    }
  }

  async function selectCustomer(id) {
    currentCustomerId = id;
    sessionId = null;
    document.getElementById('searchResults').innerHTML = '';
    document.getElementById('searchResults').style.display = 'none';

    // Reset chat
    clearChat();
    document.getElementById('chatInput').disabled = false;
    document.getElementById('chatSend').disabled = false;

    // Show skeletons
    ['profileCard', 'trustGaugeCard', 'recsCard', 'notesCard'].forEach(x => {
      document.getElementById(x).classList.remove('hidden');
    });

    try {
      const d = await api.get(`/customer/summary/${id}`);
      if (d.status !== 'ok') {
        showToast('Customer not found', 'error'); return;
      }
      renderProfile(d);
      renderTrustGauge(d.trust_score);
      renderRecommendations(d.recommendations);
      renderNotes(d.rag_interaction_notes);
    } catch (e) {
      showToast('Failed to load customer', 'error');
    }
  }

  function renderProfile(d) {
    const p = d.profile || {};
    const risk = d.risk_profile || {};
    const name = p.name || '—';

    document.getElementById('profileAvatar').textContent = name[0] || '?';
    document.getElementById('profileName').textContent = name;
    document.getElementById('profileMeta').textContent =
      `${p.account_type || '—'} · Age ${p.age || '—'} · Customer #${p.customer_id || '—'}`;
    document.getElementById('statBalance').textContent = fmt$(p.balance);
    document.getElementById('statCredit').textContent = p.credit_score || '—';
    document.getElementById('statType').textContent = (p.account_type || '—').charAt(0).toUpperCase() + (p.account_type || '').slice(1);
    document.getElementById('statRetention').textContent =
      risk.retention_probability ? `${(risk.retention_probability * 100).toFixed(0)}%` : '—';

    // Risk badge
    const riskLevel = p.risk_level || risk.risk_level || 'Unknown';
    const badge = document.getElementById('riskBadge');
    badge.textContent = riskLevel;
    badge.className = `badge ${riskLevel === 'Low' ? 'badge-green' : riskLevel === 'High' ? 'badge-red' : 'badge-amber'}`;

    // Update search box
    document.getElementById('customerSearch').value = name;
  }

  function renderTrustGauge(trustScore) {
    if (!trustScore) return;
    const score = Math.round(trustScore.score || 0);
    const tier = trustScore.tier || '—';
    drawGauge('gaugeArc', 'gaugeValue', 'gaugeTier', score, tier);
    renderTrustBars('trustComponentBars', trustScore.components);
  }

  function renderRecommendations(recs) {
    const el = document.getElementById('recsList');
    if (!recs || !recs.length) { el.innerHTML = '<p style="color:var(--t3);font-size:.8rem">No recommendations.</p>'; return; }
    el.innerHTML = recs.slice(0, 3).map(r => `
      <div class="rec-item">
        <div class="rec-title">💳 ${r.product || r.type || 'Product'}</div>
        <div class="rec-reason">${r.reason || ''}</div>
      </div>`).join('');
  }

  function renderNotes(notes) {
    const el = document.getElementById('notesList');
    const badge = document.getElementById('notesBadge');
    if (!notes || !notes.length) {
      el.innerHTML = '<p style="color:var(--t3);font-size:.8rem">No recent notes.</p>';
      if (badge) badge.textContent = '0';
      return;
    }
    if (badge) badge.textContent = notes.length;
    el.innerHTML = notes.slice(0, 5).map(n => `
      <div class="note-item">
        <div>${n.content || n.text || n.banker_notes || JSON.stringify(n)}</div>
        <div class="note-date">${fmtDate(n.timestamp || n.date)}</div>
      </div>`).join('');
  }

  // ── Chat ─────────────────────────────────────────────────
  async function sendMessage() {
    const input = document.getElementById('chatInput');
    const q = input.value.trim();
    if (!q) return;
    input.value = '';

    const msgs = document.getElementById('chatMessages');

    // Clear empty state on first message
    const empty = msgs.querySelector('.chat-empty');
    if (empty) empty.remove();

    // User bubble
    msgs.innerHTML += `<div class="chat-bubble user">${escHtml(q)}</div>`;
    scrollChat();

    // Thinking bubble
    const thinkId = 'think-' + Date.now();
    msgs.innerHTML += `<div class="chat-bubble assistant" id="${thinkId}">
      <div class="loading-state" style="padding:0;gap:8px;justify-content:flex-start">
        <div class="spinner"></div><span style="color:var(--t2)">Thinking…</span>
      </div>
    </div>`;
    scrollChat();

    try {
      const body = { question: q };
      if (currentCustomerId) body.customer_id = currentCustomerId;
      if (sessionId) body.session_id = sessionId;

      const d = await api.post('/chat', body);
      sessionId = d.session_id || sessionId;

      const think = document.getElementById(thinkId);
      if (think) {
        const trust = d.ai_trust_score ? Math.round(d.ai_trust_score) : null;
        const sources = (d.sources || []).slice(0, 4);
        const srcHtml = sources.length ? `
          <details class="bubble-sources">
            <summary>📎 ${sources.length} source${sources.length > 1 ? 's' : ''}</summary>
            <div style="margin-top:6px">${sources.map(s => `<span class="source-pill">${s.source || s.doc_type || 'doc'}</span>`).join('')}</div>
          </details>` : '';

        const trustHtml = trust !== null ? `
          <div class="bubble-trust">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" stroke="currentColor" stroke-width="2"/></svg>
            AI Trust Score: <strong style="color:${trust>=71?'#10b981':trust>=41?'#f59e0b':'#ef4444'}">${trust}/100</strong>
            <span class="badge ${d.trust_tier==='Trusted'?'badge-green':d.trust_tier==='Moderate'?'badge-amber':'badge-red'}" style="font-size:.6rem">${d.trust_tier||''}</span>
          </div>` : '';

        const rid = 'r' + Date.now();
        think.innerHTML = `<div>${escHtml(d.answer || 'No response.')}</div>
          ${srcHtml}${trustHtml}
          <div class="feedback-row">
            <button class="fb-btn approve" onclick="Banker.sendFeedback('approve','${rid}','${escHtml(q)}','${escHtml(d.answer||'')}')">👍 Approve</button>
            <button class="fb-btn reject" onclick="Banker.sendFeedback('reject','${rid}','${escHtml(q)}','${escHtml(d.answer||'')}')">👎 Reject</button>
          </div>`;

        // Push to Trust tab
        Trust.updateFromChat(d);
      }
    } catch (e) {
      const think = document.getElementById(thinkId);
      if (think) think.innerHTML = `<span style="color:var(--red)">⚠️ Error: ${e.message}</span>`;
    }
    scrollChat();
  }

  async function sendFeedback(type, responseId, prompt, response) {
    if (!sessionId) return;
    try {
      await api.post('/feedback', {
        session_id: sessionId,
        response_id: responseId,
        feedback_type: type,
        prompt: prompt,
        response_text: response,
        model_used: 'gpt-4',
        trust_score: 75,
      });
      showToast(type === 'approve' ? '👍 Feedback recorded' : '👎 Feedback recorded');
    } catch { /* silent */ }
  }

  function clearChat() {
    const msgs = document.getElementById('chatMessages');
    msgs.innerHTML = `<div class="chat-empty">
      <div class="chat-empty-icon">🤖</div>
      <p>Search for a customer, then ask the AI copilot about their profile, policies, or transactions.</p>
      <div class="chat-suggestions">
        <button class="chip" data-q="What is the AML policy for large transactions?">AML policy</button>
        <button class="chip" data-q="What are wire transfer limits?">Wire limits</button>
        <button class="chip" data-q="Summarise this customer's risk profile.">Risk summary</button>
      </div>
    </div>`;
    msgs.querySelectorAll('.chat-suggestions .chip').forEach(c => {
      c.addEventListener('click', () => {
        document.getElementById('chatInput').value = c.dataset.q;
        sendMessage();
      });
    });
    sessionId = null;
  }

  function scrollChat() {
    const el = document.getElementById('chatMessages');
    if (el) el.scrollTop = el.scrollHeight;
  }

  function escHtml(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function showToast(msg, type = 'ok') {
    const t = document.createElement('div');
    t.textContent = msg;
    Object.assign(t.style, {
      position:'fixed', bottom:'24px', right:'24px', zIndex:'999',
      padding:'10px 18px', borderRadius:'10px', fontSize:'.82rem', fontWeight:'600',
      background: type === 'error' ? '#ef4444' : '#10b981', color:'#fff',
      boxShadow:'0 4px 14px rgba(0,0,0,.4)', transition:'opacity .3s',
    });
    document.body.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 2500);
  }

  document.addEventListener('DOMContentLoaded', initSearch);

  return { selectCustomer, sendMessage, sendFeedback, clearChat };
})();
