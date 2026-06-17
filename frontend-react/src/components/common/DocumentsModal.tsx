import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { documentsApi, type PolicyDoc } from '@/services/api';

// ── Markdown-like renderer ────────────────────────────────────────────────────
function DocRenderer({ content }: { content: string }) {
  const lines = content.split('\n');
  return (
    <div className="prose prose-invert max-w-none text-[13px] leading-relaxed">
      {lines.map((line, i) => {
        const t = line.trim();
        if (!t) return <div key={i} className="h-2" />;
        // ALL-CAPS line = section heading
        if (t === t.toUpperCase() && t.length > 4 && /[A-Z]/.test(t)) {
          return (
            <h3 key={i} className="text-[11px] font-bold text-purple-300 uppercase tracking-widest mt-6 mb-2 pb-1.5 border-b border-purple-500/20">
              {t}
            </h3>
          );
        }
        // Numbered item
        if (/^\d+[\.\)]\s/.test(t)) {
          return (
            <p key={i} className="text-t2 pl-4 my-0.5 before:content-[''] flex gap-2">
              <span className="text-purple-400/60 flex-shrink-0 font-mono text-[11px]">{t.match(/^(\d+[\.\)])/)?.[1]}</span>
              <span>{t.replace(/^\d+[\.\)]\s*/, '')}</span>
            </p>
          );
        }
        // Bullet
        if (/^[-•]\s/.test(t)) {
          return (
            <div key={i} className="flex gap-2 my-0.5 pl-2">
              <span className="text-purple-400 mt-1 flex-shrink-0">·</span>
              <p className="text-t2 m-0">{t.replace(/^[-•]\s*/, '')}</p>
            </div>
          );
        }
        return <p key={i} className="text-t2 my-0.5">{t}</p>;
      })}
    </div>
  );
}

// ── Category badge ────────────────────────────────────────────────────────────
const CAT_COLOR: Record<string, string> = {
  Policy:     'bg-purple-500/10 text-purple-300 border-purple-500/20',
  Compliance: 'bg-red-500/10 text-red-300 border-red-500/20',
  Products:   'bg-blue-500/10 text-blue-300 border-blue-500/20',
  Operations: 'bg-amber-500/10 text-amber-300 border-amber-500/20',
  Reference:  'bg-green-500/10 text-green-300 border-green-500/20',
};

// ── Main component ────────────────────────────────────────────────────────────
interface Props { onClose: () => void; }

export default function DocumentsModal({ onClose }: Props) {
  const [docs, setDocs]         = useState<PolicyDoc[]>([]);
  const [loading, setLoading]   = useState(true);
  const [selected, setSelected] = useState<PolicyDoc | null>(null);
  const [content, setContent]   = useState<string>('');
  const [reading, setReading]   = useState(false);
  const [search, setSearch]     = useState('');
  const [activecat, setActiveCat] = useState<string>('All');

  useEffect(() => {
    documentsApi.list()
      .then(r => { setDocs(r.documents); if (r.documents.length) openDoc(r.documents[0]); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const openDoc = useCallback(async (doc: PolicyDoc) => {
    setSelected(doc);
    setReading(true);
    setContent('');
    try {
      const r = await documentsApi.content(doc.filename);
      setContent(r.content);
    } catch { setContent('Error loading document.'); }
    finally { setReading(false); }
  }, []);

  const categories = ['All', ...Array.from(new Set(docs.map(d => d.category)))];

  const filtered = docs.filter(d => {
    const matchCat = activecat === 'All' || d.category === activecat;
    const matchQ   = !search || d.title.toLowerCase().includes(search.toLowerCase());
    return matchCat && matchQ;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1,    y: 0  }}
        exit={{ opacity: 0,  scale: 0.96, y: 12  }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-6xl h-[88vh] bg-[#0c0c14] border border-white/[0.08] rounded-2xl shadow-2xl flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/[0.06] flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-base">📄</div>
            <div>
              <h2 className="text-sm font-semibold text-t1">Policy Documents</h2>
              <p className="text-[10px] text-t3">{docs.length} documents · TrustNova Bank internal library</p>
            </div>
          </div>
          <button onClick={onClose}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-t3 hover:text-red-400 hover:bg-red-500/10 transition-all border border-white/[0.06]">
            ✕
          </button>
        </div>

        <div className="flex flex-1 min-h-0">
          {/* Sidebar */}
          <div className="w-64 flex-shrink-0 border-r border-white/[0.06] flex flex-col">
            {/* Search + filter */}
            <div className="p-3 space-y-2 border-b border-white/[0.04]">
              <input
                type="text" value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Search documents…"
                className="w-full h-7 px-3 text-xs rounded-lg bg-white/[0.04] border border-white/[0.08] text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40"
              />
              <div className="flex gap-1 flex-wrap">
                {categories.map(cat => (
                  <button key={cat} onClick={() => setActiveCat(cat)}
                    className={`text-[9px] px-2 py-0.5 rounded-full border transition-all flex-shrink-0
                      ${activecat === cat
                        ? 'bg-purple-500/15 border-purple-500/30 text-purple-300'
                        : 'border-white/[0.06] text-t3 hover:text-t2'}`}>
                    {cat}
                  </button>
                ))}
              </div>
            </div>

            {/* Doc list */}
            <div className="flex-1 overflow-y-auto py-1">
              {loading ? (
                <div className="flex justify-center py-8">
                  <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : filtered.map(doc => {
                const isActive = selected?.filename === doc.filename;
                return (
                  <button key={doc.filename} onClick={() => openDoc(doc)}
                    className={`w-full flex items-start gap-2.5 px-3 py-2.5 text-left transition-all border-l-2
                      ${isActive
                        ? 'bg-purple-500/10 border-l-purple-500 border-b border-b-white/[0.04]'
                        : 'border-l-transparent hover:bg-white/[0.03] border-b border-b-white/[0.03]'}`}>
                    <span className="text-base flex-shrink-0 mt-0.5">{doc.icon}</span>
                    <div className="min-w-0">
                      <div className={`text-xs font-medium leading-tight truncate ${isActive ? 'text-purple-300' : 'text-t1'}`}>
                        {doc.title}
                      </div>
                      <div className="flex items-center gap-1.5 mt-1">
                        <span className={`text-[9px] px-1.5 py-0.5 rounded border ${CAT_COLOR[doc.category] ?? 'bg-white/[0.04] text-t3 border-white/[0.06]'}`}>
                          {doc.category}
                        </span>
                        <span className="text-[9px] text-t3">{doc.size_kb} KB</span>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Reader pane */}
          <div className="flex-1 flex flex-col min-w-0">
            {selected ? (
              <>
                {/* Doc header */}
                <div className="px-6 py-3.5 border-b border-white/[0.06] flex-shrink-0 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{selected.icon}</span>
                    <div>
                      <h3 className="text-sm font-semibold text-t1">{selected.title}</h3>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className={`text-[9px] px-2 py-0.5 rounded-full border ${CAT_COLOR[selected.category] ?? 'bg-white/[0.04] text-t3 border-white/[0.06]'}`}>
                          {selected.category}
                        </span>
                        <span className="text-[9px] text-t3">{selected.size_kb} KB · {selected.lines} lines · {selected.sections} sections</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {/* Prev / Next navigation */}
                    {(() => {
                      const idx = filtered.findIndex(d => d.filename === selected.filename);
                      return (
                        <>
                          <button disabled={idx <= 0} onClick={() => idx > 0 && openDoc(filtered[idx - 1])}
                            className="text-[10px] px-2 py-1 rounded-lg border border-white/[0.06] text-t3 hover:text-t1 disabled:opacity-30 transition-all">
                            ← Prev
                          </button>
                          <span className="text-[10px] text-t3">{idx + 1} / {filtered.length}</span>
                          <button disabled={idx >= filtered.length - 1} onClick={() => idx < filtered.length - 1 && openDoc(filtered[idx + 1])}
                            className="text-[10px] px-2 py-1 rounded-lg border border-white/[0.06] text-t3 hover:text-t1 disabled:opacity-30 transition-all">
                            Next →
                          </button>
                        </>
                      );
                    })()}
                  </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto px-8 py-6">
                  <AnimatePresence mode="wait">
                    {reading ? (
                      <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        className="flex flex-col items-center justify-center h-40 gap-3">
                        <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                        <p className="text-xs text-t3">Loading {selected.title}…</p>
                      </motion.div>
                    ) : (
                      <motion.div key={selected.filename} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.2 }}>
                        <DocRenderer content={content} />
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-center gap-3">
                <div className="text-4xl">📄</div>
                <p className="text-sm text-t3">Select a document to read</p>
              </div>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
