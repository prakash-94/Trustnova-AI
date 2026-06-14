import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { fraudApi } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';

const riskColor: Record<string, string> = { low: '#10b981', medium: '#f59e0b', high: '#ef4444', critical: '#dc2626' };
const fmt = (cents: number) => `$${(cents / 100).toLocaleString()}`;

export default function FraudMonitor() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [riskFilter, setRiskFilter] = useState('');

  const load = async () => {
    setLoading(true);
    const [a, s] = await Promise.all([
      fraudApi.alerts({ risk_level: riskFilter || undefined }),
      fraudApi.summary(),
    ]);
    setAlerts(a.alerts ?? []);
    setSummary(s);
    setLoading(false);
  };

  useEffect(() => { load(); }, [riskFilter]);

  const dismiss = async (id: string) => {
    await fraudApi.dismiss(id);
    load();
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold gradient-text">Fraud Monitor</h1>
          <p className="text-white/40 text-sm">Real-time fraud detection and alert management</p>
        </div>
        <select value={riskFilter} onChange={e => setRiskFilter(e.target.value)} className="text-sm px-3 py-2">
          <option value="">All Risk Levels</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Alerts', value: summary.total_alerts ?? 0, color: '#7c3aed' },
            { label: 'High Risk', value: (summary.by_risk?.high ?? 0) + (summary.by_risk?.critical ?? 0), color: '#ef4444' },
            { label: 'Flagged Today', value: summary.flagged_today ?? 0, color: '#f59e0b' },
            { label: 'Fraud Rate', value: `${((summary.fraud_rate ?? 0) * 100).toFixed(2)}%`, color: '#3b82f6' },
          ].map(s => (
            <GlassCard key={s.label} className="text-center">
              <div className="text-2xl font-bold" style={{ color: s.color }}>{s.value}</div>
              <div className="text-xs text-white/40 mt-1">{s.label}</div>
            </GlassCard>
          ))}
        </div>
      )}

      <div className="space-y-2">
        {loading ? (
          <div className="text-white/30 text-sm py-8 text-center">Loading alerts…</div>
        ) : alerts.map((a, i) => (
          <motion.div key={a.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
            <GlassCard className="flex items-start gap-4">
              <div className="w-2 h-2 rounded-full mt-2 flex-shrink-0"
                style={{ background: riskColor[a.risk_level ?? 'low'] }} />
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                    style={{ background: `${riskColor[a.risk_level ?? 'low']}22`, color: riskColor[a.risk_level ?? 'low'] }}>
                    {a.risk_level}
                  </span>
                  <span className="text-xs text-white/30">{a.alert_type}</span>
                  <span className="text-xs text-white/20">{a.created_at?.slice(0,16)?.replace('T',' ')}</span>
                </div>
                <div className="text-sm text-white/80 mt-1">{a.flag_reason || a.description}</div>
                <div className="text-xs text-white/40 mt-0.5">
                  {a.merchant && `${a.merchant} · `}{a.amount_cents ? fmt(a.amount_cents) : ''}{a.location ? ` · ${a.location}` : ''}
                </div>
              </div>
              <button onClick={() => dismiss(a.id)}
                className="text-xs px-3 py-1.5 rounded-lg bg-white/5 text-white/40 hover:text-white/70 hover:bg-white/10 transition-all flex-shrink-0">
                Dismiss
              </button>
            </GlassCard>
          </motion.div>
        ))}
        {!loading && alerts.length === 0 && (
          <div className="text-white/30 text-sm py-12 text-center">
            <div className="text-4xl mb-3">✓</div>
            No fraud alerts for selected filter
          </div>
        )}
      </div>
    </div>
  );
}
