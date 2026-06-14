import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { amlApi } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';

const riskColor: Record<string, string> = { low: '#10b981', medium: '#f59e0b', high: '#ef4444', critical: '#dc2626' };
const statusColor: Record<string, string> = { open: '#ef4444', investigating: '#f59e0b', closed: '#94a3b8', escalated: '#dc2626', resolved: '#10b981' };

export default function AMLCenter() {
  const [cases, setCases] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    const [c, s] = await Promise.all([
      amlApi.cases({ status: statusFilter || undefined }),
      amlApi.stats(),
    ]);
    setCases(c.cases ?? []);
    setStats(s);
    setLoading(false);
  };

  useEffect(() => { load(); }, [statusFilter]);

  const updateCase = async (id: number, status: string) => {
    await amlApi.updateCase(id, { status });
    load();
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold gradient-text">AML Monitoring</h1>
          <p className="text-white/40 text-sm">Anti-money laundering case management</p>
        </div>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="text-sm px-3 py-2">
          <option value="">All Statuses</option>
          <option value="open">Open</option>
          <option value="investigating">Investigating</option>
          <option value="escalated">Escalated</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[
            { label: 'Total', value: stats.total, color: '#7c3aed' },
            { label: 'Open', value: stats.open, color: '#ef4444' },
            { label: 'Investigating', value: stats.investigating, color: '#f59e0b' },
            { label: 'Escalated', value: stats.escalated, color: '#dc2626' },
            { label: 'Resolved', value: stats.resolved, color: '#10b981' },
          ].map(s => (
            <GlassCard key={s.label} className="text-center">
              <div className="text-2xl font-bold" style={{ color: s.color }}>{s.value ?? 0}</div>
              <div className="text-xs text-white/40 mt-1">{s.label}</div>
            </GlassCard>
          ))}
        </div>
      )}

      <div className="space-y-2">
        {loading ? (
          <div className="text-white/30 text-sm py-8 text-center">Loading…</div>
        ) : cases.map((c, i) => (
          <motion.div key={c.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
            <GlassCard className="space-y-2">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{ background: `${statusColor[c.status] ?? '#94a3b8'}22`, color: statusColor[c.status] ?? '#94a3b8' }}>
                      {c.status}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full"
                      style={{ background: `${riskColor[c.risk_level] ?? '#94a3b8'}22`, color: riskColor[c.risk_level] ?? '#94a3b8' }}>
                      {c.risk_level}
                    </span>
                    <span className="text-xs text-white/30">{c.case_number}</span>
                  </div>
                  <div className="text-sm font-medium text-white/80 mt-1">{c.alert_type}</div>
                  <div className="text-xs text-white/40">{c.description}</div>
                </div>
                <div className="flex gap-1 flex-shrink-0">
                  {c.status === 'open' && (
                    <button onClick={() => updateCase(c.id, 'investigating')}
                      className="text-xs px-2 py-1 rounded-lg bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30 transition-all">
                      Investigate
                    </button>
                  )}
                  {(c.status === 'investigating' || c.status === 'open') && (
                    <button onClick={() => updateCase(c.id, 'resolved')}
                      className="text-xs px-2 py-1 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-all">
                      Resolve
                    </button>
                  )}
                </div>
              </div>
            </GlassCard>
          </motion.div>
        ))}
        {!loading && cases.length === 0 && <div className="text-white/30 text-sm py-8 text-center">No AML cases found</div>}
      </div>
    </div>
  );
}
