/* ============================================================
   Banker Copilot — Customer search, profile, chat, recommendations
   ============================================================ */

const Banker = (() => {
  let currentCustomerId = null;
  let sessionId = null;
  let searchTimeout = null;

  // --- Init ---
  document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('customerSearch');
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => searchCustomers(searchInput.value.trim()), 300);
    });
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') searchCustomers(searchInput.value.trim());
    });

    document.getElementById('chatInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) sendChat();
    });
    document.getElementById('chatSend').addEventListener('click', sendChat);
  });

  // --- Customer Search ---
  async function searchCustomers(query) {
    if (!query || query.length < 2) {
      document.getElementById('searchResults').innerHTML = '';
      return;
    }
    try {
      const data = await api.get(`/customer/search?q=${encodeURIComponent(query)}&limit=5`);
      if (data.status === 'ok' && data.results && data.results.length > 0) {
        document.getElementById('searchResults').innerHTML = data.results.map(c => `
          <div class="alert-item" onclick="Banker.loadCustomer('${c.customer_id}')" style="cursor:pointer;">
            <div class="profile-avatar" style="width:32px;height:32px;font-size:0.8rem;border-radius:8px;">${(c.name || '?')[0]}</div>
            <div class="alert-info">
              <div class="alert-title">${c.name || c.customer_id}</div>
              <div class="alert-meta">${c.account_type || ''} | ${formatCurrency(c.balance)}</div>
            </div>
          </div>
        `).join('');
      } else {
        // Try direct ID lookup
        document.getElementById('searchResults').innerHTML = `
          <div class="alert-item" onclick="Banker.loadCustomer('${query}')" style="cursor:pointer;">
            <div class="alert-info"><div class="alert-title">Search for: ${query}</div>
            <div class="alert-meta">Click to load by ID</div></div>
          </div>`;
      }
    } catch {
      document.getElementById('searchResults').innerHTML = `
        <div class="alert-item" onclick="Banker.loadCustomer('${query}')" style="cursor:pointer;">
          <div class="alert-info"><div class="alert-title">Load: ${query}</div></div>
        </div>`;
    }
  }

  // --- Load Customer ---
  async function loadCustomer(customerId) {
    currentCustomerId = customerId;
    sessionId = null;
    document.getElementById('searchResults').innerHTML = '';
    document.getElementById('customerSearch').value = customerId;

    try {
      const data = await api.get(`/customer/summary/${customerId}`);
      if (data.status !== 'ok') {
        alert(`Customer not found: ${data.error || customerId}`);
        return;
      }
      renderProfile(data);
      renderTrustGauge(data.trust_score);
      renderRecommendations(data.recommendations);
      renderNotes(data.rag_interaction_notes);
      enableChat();
    } catch (err) {
      alert(`Error loading customer: ${err.message}`);
    }
  }

  function renderProfile(data) {
    const p = data.profile || {};
    document.getElementById('profileCard').style.display = '';
    document.getElementById('profileAvatar').textContent = (p.name || '?')[0];
    document.getElementById('profileName').textContent = p.name || data.customer_id;
    document.getElementById('profileSubtitle').textContent = `ID: ${data.customer_id} | Age: ${p.age || '—'}`;
    document.getElementById('statBalance').textContent = formatCurrency(p.balance);
    document.getElementById('statCredit').textContent = p.credit_score || '—';
    document.getElementById('statType').textContent = (p.account_type || '—').charAt(0).toUpperCase() + (p.account_type || '').slice(1);

    // Risk badge
    const risk = data.risk_profile;
    const badge = document.getElementById('riskBadge');
    if (risk) {
      const level = risk.risk_level || 'Low';
      badge.className = `badge ${level === 'High' ? 'badge-red' : level === 'Medium' ? 'badge-amber' : 'badge-green'}`;
      badge.textContent = level + ' Risk';
      document.getElementById('statRetention').textContent = risk.retention_probability
        ? (risk.retention_probability * 100).toFixed(0) + '%' : '—';
    } else {
      badge.className = 'badge badge-blue';
      badge.textContent = 'N/A';
      document.getElementById('statRetention').textContent = '—';
    }
  }

  function renderTrustGauge(trustData) {
    document.getElementById('trustGaugeCard').style.display = '';
    if (trustData && trustData.score !== undefined) {
      drawGauge('gaugeArc', 'gaugeValue', 'gaugeTier', Math.round(trustData.score), trustData.tier);
    } else {
      document.getElementById('gaugeValue').textContent = '—';
      document.getElementById('gaugeTier').textContent = 'No data';
    }
  }

  function renderRecommendations(recs) {
    const card = document.getElementById('recsCard');
    const list = document.getElementById('recsList');
    if (!recs || recs.length === 0) { card.style.display = 'none'; return; }
    card.style.display = '';
    list.innerHTML = recs.map((r, i) => `
      <div class="rec-item">
        <div class="rec-title">
          <span class="badge badge-cyan">${i + 1}</span> ${r.product}
        </div>
        <div class="rec-reason">${r.reason}</div>
        <div class="rec-confidence">
          Confidence: ${(r.confidence * 100).toFixed(0)}% | ${r.category}
        </div>
      </div>
    `).join('');
  }

  function renderNotes(notes) {
    const card = document.getElementById('notesCard');
    const list = document.getElementById('notesList');
    if (!notes || notes.length === 0) { card.style.display = 'none'; return; }
    card.style.display = '';
    list.innerHTML = notes.slice(0, 3).map(n => `
      <div class="note-item">
        ${typeof n === 'string' ? n : n.text || n.content || JSON.stringify(n)}
        <div class="note-date">${n.date || ''}</div>
      </div>
    `).join('');
  }

  // --- Chat ---
  function enableChat() {
    document.getElementById('chatInput').disabled = false;
    document.getElementById('chatSend').disabled = false;
    document.getElementById('chatMessages').innerHTML = `
      <div class="chat-msg assistant">
        Customer <strong>${currentCustomerId}</strong> loaded. Ask me anything about their profile, transactions, policies, or risk assessment.
      </div>`;
  }

  async function sendChat() {
    const input = document.getElementById('chatInput');
    const question = input.value.trim();
    if (!question) return;

    input.value = '';
    appendMsg('user', question);

    // Show typing indicator
    const typingId = 'typing-' + Date.now();
    appendMsg('assistant', '<div class="spinner" style="width:18px;height:18px;"></div> Thinking...', typingId);

    try {
      const data = await api.post('/chat', {
        question,
        customer_id: currentCustomerId,
        session_id: sessionId,
      });

      // Remove typing indicator
      const typingEl = document.getElementById(typingId);
      if (typingEl) typingEl.remove();

      if (data.status === 'ok') {
        sessionId = data.session_id;
        let html = data.answer || 'No response.';

        // Trust score inline
        if (data.ai_trust_score !== null && data.ai_trust_score !== undefined) {
          const score = Math.round(data.ai_trust_score);
          const color = score >= 71 ? '#10b981' : score >= 41 ? '#f59e0b' : '#ef4444';
          html += `<div class="trust-inline">
            <span style="color:${color};font-weight:700;">Trust: ${score}/100</span>
            <span class="badge badge-purple" style="font-size:0.65rem;">${data.model_used || 'GPT-4'}</span>
          </div>`;
        }

        // Sources
        if (data.sources && data.sources.length > 0) {
          html += `<div class="chat-sources"><details><summary>${data.sources.length} source(s)</summary>`;
          data.sources.forEach(s => {
            html += `<div class="source-item">${s.source} ${s.doc_type ? '(' + s.doc_type + ')' : ''}</div>`;
          });
          html += '</details></div>';
        }

        appendMsg('assistant', html);

        // Update AI Trust dashboard data
        if (data.ai_trust_score !== null) {
          Trust.updateFromChat(data);
        }
      } else {
        appendMsg('assistant', `Error: ${data.error || 'Unknown error'}`);
      }
    } catch (err) {
      const typingEl = document.getElementById(typingId);
      if (typingEl) typingEl.remove();
      appendMsg('assistant', `Error: ${err.message}`);
    }
  }

  function appendMsg(role, html, id) {
    const container = document.getElementById('chatMessages');
    // Remove empty state
    const empty = container.querySelector('.empty-state');
    if (empty) empty.remove();

    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;
    div.innerHTML = html;
    if (id) div.id = id;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  return { loadCustomer, searchCustomers };
})();
