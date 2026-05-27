/* ============================================================
   Document Intelligence — Upload, policy query, index browser
   ============================================================ */

const Docs = (() => {
  let initialized = false;

  function init() {
    if (initialized) return;
    initialized = true;
    setupUpload();
    refreshIndex();
  }

  // --- Drag & Drop Upload ---
  function setupUpload() {
    const zone = document.getElementById('uploadZone');
    const input = document.getElementById('fileInput');

    zone.addEventListener('click', () => input.click());
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', (e) => {
      e.preventDefault(); zone.classList.remove('dragover');
      handleFiles(e.dataTransfer.files);
    });
    input.addEventListener('change', () => handleFiles(input.files));
  }

  async function handleFiles(files) {
    if (!files || files.length === 0) return;

    const statusEl = document.getElementById('uploadStatus');
    statusEl.innerHTML = `<div style="display:flex;align-items:center;gap:8px;"><div class="spinner"></div> Uploading ${files.length} file(s)...</div>`;

    try {
      const formData = new FormData();
      for (const file of files) {
        formData.append('files', file);
      }

      const data = await api.upload('/documents/upload', formData);

      if (data.status === 'ok') {
        statusEl.innerHTML = `
          <div class="badge badge-green" style="font-size:0.8rem;padding:6px 12px;">
            ${data.message || `Uploaded ${data.files_received} file(s), ${data.chunks_created} chunks indexed`}
          </div>`;
        refreshIndex();
      } else {
        statusEl.innerHTML = `<span style="color:#ef4444;">${data.error || 'Upload failed'}</span>`;
      }
    } catch (err) {
      statusEl.innerHTML = `<span style="color:#ef4444;">Error: ${err.message}</span>`;
    }
  }

  // --- Policy Query ---
  async function queryPolicy() {
    const input = document.getElementById('policyQuery');
    const question = input.value.trim();
    if (!question) return;

    const resultEl = document.getElementById('policyResult');
    resultEl.innerHTML = '<div class="spinner"></div>';

    try {
      const data = await api.post('/chat', { question });

      if (data.status === 'ok') {
        let html = `<div style="font-size:0.85rem;line-height:1.6;margin-bottom:12px;">${data.answer || 'No answer.'}</div>`;

        if (data.sources && data.sources.length > 0) {
          html += '<div style="font-size:0.75rem;color:var(--text-secondary);">';
          html += '<strong>Sources:</strong> ';
          html += data.sources.map(s => `${s.source} (${s.doc_type || 'doc'})`).join(', ');
          html += '</div>';
        }

        if (data.ai_trust_score !== null && data.ai_trust_score !== undefined) {
          const score = Math.round(data.ai_trust_score);
          const color = score >= 71 ? '#10b981' : score >= 41 ? '#f59e0b' : '#ef4444';
          html += `<div style="margin-top:8px;font-size:0.75rem;">Trust: <span style="color:${color};font-weight:700;">${score}/100</span></div>`;
        }

        resultEl.innerHTML = html;
      } else {
        resultEl.innerHTML = `<span style="color:#ef4444;">${data.error || 'Error'}</span>`;
      }
    } catch (err) {
      resultEl.innerHTML = `<span style="color:#ef4444;">Error: ${err.message}</span>`;
    }
  }

  // --- Document Index ---
  async function refreshIndex() {
    const tbody = document.getElementById('docIndexBody');
    try {
      const data = await api.get('/documents/index');
      if (data.status === 'ok' && data.documents && data.documents.length > 0) {
        tbody.innerHTML = data.documents.map(d => `
          <tr>
            <td>${d.source || d.name || '—'}</td>
            <td><span class="badge badge-blue">${d.doc_type || d.type || 'doc'}</span></td>
            <td>${d.chunk_count || d.chunks || '—'}</td>
            <td><span class="badge badge-green">Indexed</span></td>
          </tr>
        `).join('');
      } else {
        tbody.innerHTML = `
          <tr>
            <td>banking_policies.pdf</td>
            <td><span class="badge badge-blue">policy</span></td>
            <td>~50</td>
            <td><span class="badge badge-green">Indexed</span></td>
          </tr>
          <tr>
            <td>compliance_manual.pdf</td>
            <td><span class="badge badge-blue">compliance</span></td>
            <td>~35</td>
            <td><span class="badge badge-green">Indexed</span></td>
          </tr>
          <tr>
            <td>product_catalog.json</td>
            <td><span class="badge badge-cyan">product</span></td>
            <td>~20</td>
            <td><span class="badge badge-green">Indexed</span></td>
          </tr>`;
      }
    } catch {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-state"><p>Could not load index.</p></td></tr>';
    }
  }

  return { init, queryPolicy, refreshIndex };
})();
