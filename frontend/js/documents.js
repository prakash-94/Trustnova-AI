/* ── documents.js — Upload, policy query, index browser ── */
const Docs = (() => {
  let initialized = false;

  function init() {
    if (initialized) return;
    initialized = true;
    setupUpload();
    refreshIndex();
  }

  function setupUpload() {
    const zone = document.getElementById('uploadZone');
    const input = document.getElementById('fileInput');

    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', () => handleFiles(input.files));

    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag'));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('drag');
      handleFiles(e.dataTransfer.files);
    });
  }

  async function handleFiles(files) {
    if (!files || !files.length) return;
    const status = document.getElementById('uploadStatus');
    status.innerHTML = `<div class="loading-state"><div class="spinner"></div><span>Uploading ${files.length} file(s)…</span></div>`;

    const formData = new FormData();
    Array.from(files).forEach(f => formData.append('files', f));

    try {
      const d = await api.upload('/documents/upload', formData);
      const indexed = d.indexed || d.files_processed || 0;
      status.innerHTML = `<div class="chunk-item" style="border-left:3px solid var(--green);color:var(--green)">
        ✅ Successfully indexed ${indexed} document(s). Refreshing index…
      </div>`;
      await refreshIndex();
    } catch (e) {
      status.innerHTML = `<div class="chunk-item" style="border-left:3px solid var(--red);color:var(--red)">
        ⚠️ Upload failed: ${e.message}
      </div>`;
    }
  }

  async function queryPolicy() {
    const q = document.getElementById('policyQuery').value.trim();
    if (!q) return;
    const result = document.getElementById('policyResult');
    result.innerHTML = `<div class="loading-state"><div class="spinner"></div><span>Querying policy documents…</span></div>`;

    try {
      const d = await api.post('/chat', { question: q });
      const sources = (d.sources || []).slice(0, 4);
      const trust = d.ai_trust_score ? Math.round(d.ai_trust_score) : null;

      result.innerHTML = `
        <div class="chunk-item" style="border-left:3px solid var(--blue)">
          <div style="font-size:.85rem;line-height:1.7;color:var(--t1)">${escHtml(d.answer || 'No answer found.')}</div>
          ${trust !== null ? `<div style="margin-top:10px;font-size:.72rem;color:var(--t2)">
            🛡️ AI Trust Score: <strong style="color:${trust>=71?'#10b981':trust>=41?'#f59e0b':'#ef4444'}">${trust}/100</strong>
          </div>` : ''}
          ${sources.length ? `<div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px">
            ${sources.map(s => `<span class="source-pill">${s.source || s.doc_type || 'doc'}</span>`).join('')}
          </div>` : ''}
        </div>`;
    } catch (e) {
      result.innerHTML = `<div class="chunk-item" style="border-left:3px solid var(--red);color:var(--red)">⚠️ Query failed: ${e.message}</div>`;
    }
  }

  async function refreshIndex() {
    const tbody = document.getElementById('docIndexBody');
    tbody.innerHTML = `<tr><td colspan="4" class="loading-cell"><div class="loading-state"><div class="spinner"></div><span>Loading…</span></div></td></tr>`;

    try {
      const d = await api.get('/documents/list');
      const docs = d.documents || d.files || [];

      if (!docs.length) {
        tbody.innerHTML = `<tr><td colspan="4" class="loading-cell" style="color:var(--t3)">No documents indexed yet.</td></tr>`;
        return;
      }

      tbody.innerHTML = docs.map(doc => `<tr>
        <td>
          <div style="font-weight:600;font-size:.8rem">${doc.source || doc.filename || '—'}</div>
          <div style="font-size:.68rem;color:var(--t3)">${doc.path || ''}</div>
        </td>
        <td><span class="badge badge-blue">${doc.doc_type || doc.type || 'txt'}</span></td>
        <td>${doc.chunk_count || doc.chunks || '—'}</td>
        <td><span class="badge badge-green">✓ Indexed</span></td>
      </tr>`).join('');
    } catch {
      tbody.innerHTML = `<tr><td colspan="4" class="loading-cell" style="color:var(--red)">Failed to load index</td></tr>`;
    }
  }

  function escHtml(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  return { init, queryPolicy, refreshIndex };
})();
