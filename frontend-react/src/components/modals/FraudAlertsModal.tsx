import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { fraudApi } from '@/lib/api';

interface Alert {
  id: string;
  customer_id: string;
  transaction_id: string | null;
  fraud_type: string;
  status: string;
  severity: string;
  fraud_score: number;
  investigation_notes: string;
  amount_at_risk_cents?: number | null;
  location?: string | null;
  merchant?: string | null;
  category?: string | null;
  detection_method?: string;
  resolution?: string | null;
  created_at: string;
}

interface Summary {
  total: number; open: number; resolved: number;
  false_positive: number; under_review?: number;
  critical?: number; high?: number; total_at_risk_cents?: number;
}

const STATUS_STYLES: Record<string, string> = {
  open:           'bg-red-500/10 text-red-400 border-red-500/20',
  resolved:       'bg-green-500/10 text-green-400 border-green-500/20',
  false_positive: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  under_review:   'bg-amber-500/10 text-amber-400 border-amber-500/20',
};

const SEV_STYLES: Record<string, string> = {
  critical: 'bg-red-500/15 text-red-300 border border-red-500/20',
  high:     'bg-orange-500/15 text-orange-300 border border-orange-500/20',
  medium:   'bg-amber-500/15 text-amber-300 border border-amber-500/20',
  low:      'bg-blue-500/15 text-blue-300 border border-blue-500/20',
};

const SEV_BAR: Record<string, string> = {
  critical: 'bg-red-500',
  high:     'bg-orange-500',
  medium:   'bg-amber-500',
  low:      'bg-blue-500',
};

const fmt$ = (cents: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(cents / 100);

interface Props { onClose: () => void; }
type FilterKey = 'all' | 'open' | 'resolved' | 'false_positive' | 'under_review';

// ── Detail Panel ───────────────────────────────────────────────────────────────
function AlertDetail({ alert, onBack }: { alert: Alert; onBack: () => void }) {
  const score = Math.round(alert.fraud_score * 100);

  const rows: { label: string; value: string | null | undefined; mono?: boolean; highlight?: string }[] = [
    { label: 'Alert ID',         value: alert.id,            mono: true },
    { label: 'Customer ID',      value: alert.customer_id,   mono: true },
    { label: 'Transaction ID',   value: alert.transaction_id ?? '—', mono: true },
    { label: 'Fraud Type',       value: alert.fraud_type?.replace(/_/g, ' ') },
    { label: 'Detection Method', value: alert.detection_method ?? 'ML + Rule-based' },
    { label: 'Merchant',         value: alert.merchant ?? '—' },
    { label: 'Category',         value: alert.category ?? '—' },
    { label: 'Location',         value: alert.location ?? '—' },
    { label: 'Amount at Risk',   value: alert.amount_at_risk_cents ? fmt$(alert.amount_at_risk_cents) : '—', highlight: 'text-red-400' },
    { label: 'Resolution',       value: alert.resolution ? alert.resolution.replace(/_/g, ' ') : '—' },
    { label: 'Reported At',      value: alert.created_at?.slice(0, 16).replace('T', ' ') },
  ];

  return (
    <motion.div
      initial={{ x: 32, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 32, opacity: 0 }}
      transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col h-full"
    >
      {/* Detail header */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-white/[0.06]">
        <button onClick={onBack}
          className="flex items-center gap-1 text-[11px] text-t3 hover:text-purple-300 transition-colors px-2 py-1 rounded-lg hover:bg-white/[0.05]">
          ← Back
        </button>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold text-t1 font-mono truncate">{alert.id}</div>
          <div className="text-[10px] text-t3 mt-0.5">Alert Detail</div>
        </div>
        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold capitalize ${SEV_STYLES[alert.severity] ?? SEV_STYLES.low}`}>
          {alert.severity}
        </span>
        <span className={`px-2 py-0.5 rounded border text-[10px] font-medium ${STATUS_STYLES[alert.status] ?? 'bg-white/5 text-t3 border-white/10'}`}>
          {alert.status.replace(/_/g, ' ')}
        </span>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">

        {/* Risk Score gauge */}
        <div className="glass rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] text-t3 uppercase tracking-wider">Fraud Risk Score</span>
            <span className={`text-2xl font-bold tabular-nums ${
              score >= 85 ? 'text-red-400' : score >= 70 ? 'text-orange-400' : score >= 55 ? 'text-amber-400' : 'text-blue-400'
            }`}>{score}%</span>
          </div>
          <div className="w-full h-2 rounded-full bg-white/[0.06] overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${score}%` }}
              transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
              className={`h-full rounded-full ${SEV_BAR[alert.severity] ?? 'bg-blue-500'}`}
            />
          </div>
          <div className="flex justify-between text-[9px] text-t3 mt-1">
            <span>0%</span><span>Low 55%</span><span>Med 70%</span><span>High 85%</span><span>100%</span>
          </div>
        </div>

        {/* Investigation Notes */}
        <div>
          <div className="text-[10px] text-t3 uppercase tracking-wider mb-2">Investigation Notes</div>
          <div className="glass rounded-xl px-4 py-3 space-y-2.5">
            {(alert.investigation_notes || '').split('\n').filter(Boolean).map((line, i) => {
              const text = line.replace(/^[•\s]+/, '').trim();
              const isSla = text.startsWith('SLA');
              const isCritical = text.startsWith('SLA REQUIREMENT — CRITICAL');
              return (
                <div key={i} className={`flex gap-2.5 text-[11px] leading-relaxed ${
                  isCritical ? 'text-red-300' : isSla ? 'text-amber-300' : 'text-t2'
                }`}>
                  <span className={`flex-shrink-0 mt-0.5 font-bold ${
                    isCritical ? 'text-red-400' : isSla ? 'text-amber-400' : 'text-purple-400'
                  }`}>•</span>
                  <span>{text}</span>
                </div>
              );
            })}
            {!alert.investigation_notes && <span className="text-xs text-t3">—</span>}
          </div>
        </div>

        {/* Field grid */}
        <div>
          <div className="text-[10px] text-t3 uppercase tracking-wider mb-2">Alert Details</div>
          <div className="glass rounded-xl overflow-hidden">
            {rows.map((r, i) => (
              <div key={r.label} className={`flex items-start justify-between px-4 py-2.5 gap-4 ${i < rows.length - 1 ? 'border-b border-white/[0.04]' : ''}`}>
                <span className="text-[10px] text-t3 flex-shrink-0 w-32">{r.label}</span>
                <span className={`text-[11px] text-right break-all ${r.mono ? 'font-mono text-purple-300' : r.highlight ?? 'text-t1'}`}>
                  {r.value || '—'}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Quick actions */}
        <div>
          <div className="text-[10px] text-t3 uppercase tracking-wider mb-2">Quick Actions</div>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: 'Mark Resolved',     color: 'bg-green-500/10 border-green-500/20 text-green-400 hover:bg-green-500/20' },
              { label: 'Mark False Positive',color: 'bg-slate-500/10 border-slate-500/20 text-slate-400 hover:bg-slate-500/20' },
              { label: 'Escalate',           color: 'bg-red-500/10 border-red-500/20 text-red-400 hover:bg-red-500/20' },
              { label: 'Flag for Review',    color: 'bg-amber-500/10 border-amber-500/20 text-amber-400 hover:bg-amber-500/20' },
            ].map(a => (
              <button key={a.label}
                className={`text-[10px] px-3 py-2 rounded-lg border font-medium transition-all ${a.color}`}>
                {a.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// ── Main Modal ─────────────────────────────────────────────────────────────────
export default function FraudAlertsModal({ onClose }: Props) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [summary, setSummary] = useState<Summary>({ total: 0, open: 0, resolved: 0, false_positive: 0 });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterKey>('all');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Alert | null>(null);

  useEffect(() => {
    fraudApi.list({ limit: 300 }).then(r => {
      setAlerts(r.alerts as unknown as Alert[]);
      setSummary(r.summary as unknown as Summary);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const visible = alerts.filter(a => {
    const matchesFilter = filter === 'all' || a.status === filter;
    const q = search.toLowerCase();
    const matchesSearch = !q ||
      (a.customer_id ?? '').toLowerCase().includes(q) ||
      (a.investigation_notes ?? '').toLowerCase().includes(q) ||
      (a.id ?? '').toLowerCase().includes(q) ||
      (a.fraud_type ?? '').toLowerCase().includes(q);
    return matchesFilter && matchesSearch;
  });

  const pills: { label: string; count: number; key: FilterKey; color: string }[] = [
    { label: 'Total',          count: summary.total,             key: 'all',           color: 'bg-purple-500/10 text-purple-400' },
    { label: 'Open',           count: summary.open,              key: 'open',           color: 'bg-red-500/10 text-red-400' },
    { label: 'Under Review',   count: summary.under_review ?? 0, key: 'under_review',   color: 'bg-amber-500/10 text-amber-400' },
    { label: 'Resolved',       count: summary.resolved,          key: 'resolved',       color: 'bg-green-500/10 text-green-400' },
    { label: 'False Positive', count: summary.false_positive,    key: 'false_positive', color: 'bg-slate-500/10 text-slate-400' },
  ];

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <motion.div initial={{ scale: 0.94, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.94, opacity: 0 }} transition={{ duration: 0.2 }}
        className="glass-card w-full max-w-6xl max-h-[90vh] flex flex-col overflow-hidden">

        {/* ── Modal Header ── */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06] flex-shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-t1">🛡 Fraud Alerts</h2>
            <p className="text-[10px] text-t3 mt-0.5">
              Live from <code className="text-purple-400/80">fraud_alerts</code> table · banking.db
              {summary.critical !== undefined && summary.critical > 0 && (
                <span className="ml-2 text-red-400 font-medium">{summary.critical} critical</span>
              )}
              {summary.total_at_risk_cents != null && summary.total_at_risk_cents > 0 && (
                <span className="ml-2 text-amber-400">{fmt$(summary.total_at_risk_cents)} at risk</span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {selected && (
              <span className="text-[10px] text-purple-400 bg-purple-500/10 border border-purple-500/20 px-2 py-1 rounded-lg">
                Viewing detail
              </span>
            )}
            <button onClick={onClose}
              className="text-t3 hover:text-t1 w-7 h-7 flex items-center justify-center rounded-lg hover:bg-white/[0.06] transition-all text-lg">✕</button>
          </div>
        </div>

        {/* ── Split body ── */}
        <div className="flex flex-1 min-h-0 overflow-hidden">

          {/* LEFT — list pane */}
          <div className={`flex flex-col min-h-0 transition-all duration-300 ${selected ? 'w-[55%] border-r border-white/[0.06]' : 'w-full'}`}>
            {/* Filter pills + search */}
            <div className="px-5 py-2.5 border-b border-white/[0.04] flex gap-1.5 flex-wrap items-center flex-shrink-0">
              {pills.map(s => (
                <button key={s.key} onClick={() => setFilter(s.key)}
                  className={`px-2.5 py-1 rounded-full text-[11px] font-medium border transition-all ${s.color}
                    ${filter === s.key ? 'border-current opacity-100' : 'border-transparent opacity-50 hover:opacity-100'}`}>
                  {s.label}: <span className="font-bold">{s.count}</span>
                </button>
              ))}
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Search…"
                className="ml-auto bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-1 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 w-44" />
            </div>

            {/* Table */}
            <div className="flex-1 overflow-y-auto">
              {loading ? (
                <div className="flex items-center justify-center py-16 text-t3 text-sm gap-2">
                  <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                  Loading alerts…
                </div>
              ) : visible.length === 0 ? (
                <div className="text-center py-16 text-t3 text-xs">No alerts match the current filter.</div>
              ) : (
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-[#0c0c14] z-10">
                    <tr className="text-t3 uppercase tracking-wider border-b border-white/[0.06] text-[9px]">
                      <th className="text-left px-4 py-2 font-medium">Alert ID</th>
                      <th className="text-left px-2 py-2 font-medium">Customer</th>
                      <th className="text-left px-2 py-2 font-medium">Type</th>
                      {!selected && <th className="text-left px-2 py-2 font-medium">Notes</th>}
                      <th className="text-left px-2 py-2 font-medium">Sev.</th>
                      <th className="text-left px-2 py-2 font-medium">Score</th>
                      <th className="text-left px-2 py-2 font-medium">Status</th>
                      <th className="text-left px-2 py-2 font-medium">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map(a => {
                      const isActive = selected?.id === a.id;
                      return (
                        <tr
                          key={a.id}
                          onClick={() => setSelected(isActive ? null : a)}
                          className={`border-b border-white/[0.03] cursor-pointer transition-all group ${
                            isActive
                              ? 'bg-purple-500/10 border-l-2 border-l-purple-500'
                              : 'hover:bg-purple-500/[0.05] hover:border-l-2 hover:border-l-purple-500/40'
                          }`}
                        >
                          {/* Alert ID — clickable, styled as link */}
                          <td className="py-2.5 pl-4 pr-2">
                            <span className={`font-mono text-[11px] underline underline-offset-2 decoration-dotted transition-colors ${
                              isActive ? 'text-purple-300' : 'text-purple-400/80 group-hover:text-purple-300'
                            }`}>
                              {(a.id ?? '').slice(0, 14)}
                            </span>
                          </td>
                          <td className="py-2.5 px-2 text-t2 font-mono text-[10px]">{(a.customer_id ?? '').slice(0, 8)}</td>
                          <td className="py-2.5 px-2 text-t2 capitalize whitespace-nowrap text-[10px]">{(a.fraud_type ?? '').replace(/_/g, ' ')}</td>
                          {!selected && (
                            <td className="py-2.5 px-2 text-t3 max-w-[180px] truncate text-[10px]" title={a.investigation_notes}>
                              {a.investigation_notes}
                            </td>
                          )}
                          <td className="py-2.5 px-2">
                            <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium capitalize ${SEV_STYLES[a.severity] ?? SEV_STYLES.low}`}>
                              {a.severity}
                            </span>
                          </td>
                          <td className="py-2.5 px-2 tabular-nums text-[11px]">
                            <span className={a.fraud_score >= 0.85 ? 'text-red-400 font-bold' : a.fraud_score >= 0.70 ? 'text-orange-400' : 'text-t2'}>
                              {Math.round(a.fraud_score * 100)}%
                            </span>
                          </td>
                          <td className="py-2.5 px-2">
                            <span className={`px-1.5 py-0.5 rounded border text-[9px] font-medium ${STATUS_STYLES[a.status] ?? 'bg-white/5 text-t3 border-white/10'}`}>
                              {a.status.replace(/_/g, ' ')}
                            </span>
                          </td>
                          <td className="py-2.5 px-2 text-t3 text-[10px] whitespace-nowrap">{(a.created_at ?? '').slice(0, 10)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>

            {/* Footer */}
            <div className="px-5 py-2 border-t border-white/[0.04] text-[9px] text-t3 flex-shrink-0 flex items-center gap-3">
              <span>Showing {visible.length} of {alerts.length} alerts</span>
              {!selected && <span className="text-purple-400/50">← Click an Alert ID to view details</span>}
            </div>
          </div>

          {/* RIGHT — detail pane */}
          <AnimatePresence>
            {selected && (
              <div className="w-[45%] flex-shrink-0 overflow-hidden">
                <AlertDetail alert={selected} onBack={() => setSelected(null)} />
              </div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </motion.div>
  );
}
