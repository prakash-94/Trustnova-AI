import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { kpiApi } from '@/services/api';

interface Props { onClose: () => void; }

export default function AITrustInfoModal({ onClose }: Props) {
  const [data, setData] = useState<Awaited<ReturnType<typeof kpiApi.aiTrustInfo>> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    kpiApi.aiTrustInfo().then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const weights = data?.scoring_weights ?? {};
  const entries = data?.entries ?? [];

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <motion.div initial={{ scale: 0.94, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.94, opacity: 0 }} transition={{ duration: 0.2 }}
        className="glass-card w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden">

        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
          <div>
            <h2 className="text-sm font-semibold text-t1">✦ AI Trust Score — Data Lineage</h2>
            <p className="text-[10px] text-t3 mt-0.5">Where scores are stored and how they are computed</p>
          </div>
          <button onClick={onClose} className="text-t3 hover:text-t1 w-7 h-7 flex items-center justify-center rounded-lg hover:bg-white/[0.06] transition-all text-lg">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* Storage info */}
          <section>
            <h3 className="text-[10px] text-t3 uppercase tracking-wider mb-2">Storage</h3>
            <div className="glass rounded-xl p-4 space-y-1.5 text-xs">
              {data?.storage && Object.entries(data.storage).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <span className="text-t3 capitalize">{k.replace(/_/g, ' ')}</span>
                  <code className="text-purple-300 text-right">{v}</code>
                </div>
              ))}
            </div>
          </section>

          {/* Scoring weights */}
          <section>
            <h3 className="text-[10px] text-t3 uppercase tracking-wider mb-2">Scoring Components & Weights</h3>
            <div className="space-y-2">
              {Object.entries(weights).map(([key, cfg]) => {
                const pct = Math.round(cfg.weight * 100);
                return (
                  <div key={key} className="glass rounded-xl p-3">
                    <div className="flex justify-between mb-1">
                      <span className="text-xs text-t1 font-medium capitalize">{key.replace(/_/g, ' ')}</span>
                      <span className="text-xs font-bold text-purple-400">{pct}%</span>
                    </div>
                    <div className="w-full h-1.5 rounded-full bg-white/[0.06] mb-1.5">
                      <div className="h-full rounded-full bg-purple-500/60" style={{ width: `${pct}%` }} />
                    </div>
                    <p className="text-[10px] text-t3">{cfg.description}</p>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Tiers */}
          <section>
            <h3 className="text-[10px] text-t3 uppercase tracking-wider mb-2">Score Tiers</h3>
            <div className="grid grid-cols-2 gap-2">
              {data?.tiers && Object.entries(data.tiers).map(([tier, range]) => (
                <div key={tier} className="glass rounded-xl px-3 py-2 flex justify-between">
                  <span className="text-xs text-t2">{tier}</span>
                  <span className="text-xs font-mono text-purple-400">{range}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Recent scores */}
          <section>
            <h3 className="text-[10px] text-t3 uppercase tracking-wider mb-2">Recent Scores (last 10)</h3>
            {loading ? (
              <div className="text-xs text-t3 py-4 text-center">Loading…</div>
            ) : (
              <div className="space-y-1.5">
                {entries.map((e: Record<string, unknown>, i: number) => (
                  <div key={i} className="glass rounded-lg px-3 py-2 flex items-center gap-3">
                    <span className={`text-sm font-bold tabular-nums w-12 text-center ${
                      Number(e.final_score) >= 85 ? 'text-green-400' : Number(e.final_score) >= 70 ? 'text-amber-400' : 'text-red-400'
                    }`}>{Number(e.final_score).toFixed(0)}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-[10px] text-t1 truncate">{String(e.query)}</div>
                      <div className="text-[9px] text-t3">{String(e.session_id)} · {String(e.timestamp ?? '').slice(0, 16)}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </motion.div>
    </motion.div>
  );
}
