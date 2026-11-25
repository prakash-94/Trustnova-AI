import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { amlApi } from '@/services/api';
import GlassCard from '@/components/common/GlassCard';
import Badge from '@/components/common/Badge';
import type { AMLCase } from '@/types/banking';
import type { CustomerSummary } from '@/types';

const PAGE = 100;

const fmtUsd = (v?: number | null) =>
  v == null ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);

const fmtDate = (d?: string | null) =>
  d ? new Date(`${d.slice(0, 10)}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';

const sev = (s: string): 'red' | 'amber' | 'blue' | 'green' | 'gray' =>
  ({ critical: 'red', high: 'amber', medium: 'blue', low: 'green' } as Record<string, 'red' | 'amber' | 'blue' | 'green'>)[s] ?? 'gray';

const statusColor = (s: string): 'amber' | 'blue' | 'green' | 'red' | 'gray' =>
  ({ open: 'amber', reviewing: 'blue', resolved: 'green', escalated: 'red' } as Record<string, 'amber' | 'blue' | 'green' | 'red' | 'gray'>)[s] ?? 'gray';

const SIMULATIONS: [string, string][] = [
  ['', 'All banks'], ['HIS', 'HI-Small'], ['HIM', 'HI-Medium'], ['HIL', 'HI-Large'],
  ['LIS', 'LI-Small'], ['LIM', 'LI-Medium'], ['LIL', 'LI-Large'],
];
const FILTERS = ['all', 'open', 'reviewing', 'resolved', 'critical', 'high', 'medium', 'low'];
const SEVERITIES = new Set(['critical', 'high', 'medium', 'low']);

const titleCase = (s?: string | null) => (s ?? 'unclassified').replace(/[-_]/g, ' ');

interface AMLCenterProps {
  customer?: CustomerSummary | null;
}

export default function AMLCenter({ customer }: AMLCenterProps) {
  const [cases, setCases] = useState<AMLCase[]>([]);
  const [summary, setSummary] = useState<Record<string, number | string | null>>({});
  const [total, setTotal] = useState(0);
  const [ready, setReady] = useState(true);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AMLCase | null>(null);
  const [filter, setFilter] = useState('all');
  const [simulation, setSimulation] = useState('');

  const params = useCallback((offset: number) => ({
    customer_id: customer?.customer_id,
    simulation: simulation || undefined,
    severity: SEVERITIES.has(filter) ? filter : undefined,
    status: filter !== 'all' && !SEVERITIES.has(filter) ? filter : undefined,
    limit: PAGE,
    offset,
  }), [customer?.customer_id, simulation, filter]);

  useEffect(() => {
    // Filters can change faster than the API answers; only the latest request may update the screen.
    let stale = false;
    setLoading(true);
    setSelected(null);
    setError(null);
    amlApi.cases(params(0)).then(res => {
      if (stale) return;
      setCases(res.cases);
      setSummary(res.summary ?? {});
      setTotal(res.total ?? res.cases.length);
      setReady(res.source_ready !== false);
    }).catch(e => { if (!stale) setError(e instanceof Error ? e.message : 'Could not load AML alerts'); })
      .finally(() => { if (!stale) setLoading(false); });
    return () => { stale = true; };
  }, [params]);

  const loadMore = () => {
    setLoadingMore(true);
    amlApi.cases(params(cases.length))
      .then(res => setCases(prev => [...prev, ...res.cases]))
      .catch(() => {})
      .finally(() => setLoadingMore(false));
  };

  const num = (k: string) => Number(summary[k] ?? 0);

  return (
    <div className="space-y-4">
      {customer && (
        <GlassCard animate={false} className="px-4 py-3 border-l-2 border-amber-500/40 flex items-center gap-3">
          <span className="text-sm">🔎</span>
          <div>
            <span className="text-xs font-medium text-t1">{customer.name}</span>
            <span className="text-[10px] text-t3 ml-2">· {customer.customer_id}</span>
          </div>
          <span className="ml-auto text-[10px] text-amber-400">
            {total ? `${total} ML alerts` : 'This customer is not linked to the IBM AML accounts yet'}
          </span>
        </GlassCard>
      )}

      {/* Stat row */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { key: 'critical', label: 'Critical', color: 'red', tooltip: 'Model score ≥ 0.90: at least a 90% estimated chance the riskiest payment is laundering' },
          { key: 'high', label: 'High', color: 'amber', tooltip: 'Model score 0.70–0.89' },
          { key: 'open', label: 'Open', color: 'blue', tooltip: 'Alerts no analyst has worked yet' },
          { key: 'sar_filed', label: 'SAR Filed', color: 'purple', tooltip: 'Suspicious Activity Reports filed (filing is not connected yet)' },
        ].map((item, i) => (
          <GlassCard key={item.key} delay={i * 0.06} className="p-4 cursor-pointer group relative"
            onClick={() => item.key !== 'sar_filed' && setFilter(filter === item.key ? 'all' : item.key)}>
            <div className={`text-2xl font-bold tabular-nums text-${item.color}-400 mb-0.5`}>
              {num(item.key).toLocaleString()}
            </div>
            <div className="text-xs text-t3 uppercase tracking-wider">{item.label}</div>
            <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block w-52 px-2 py-1.5 rounded-lg bg-gray-900 border border-white/[0.08] text-[10px] text-t2 z-10 shadow-lg">
              {item.tooltip}
            </div>
          </GlassCard>
        ))}
      </div>

      <div className="grid grid-cols-5 gap-4">
        {/* Alert list */}
        <GlassCard animate={false} className="col-span-3 overflow-hidden">
          <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-t1">AML Alerts</h2>
              <p className="text-xs text-t3 truncate">
                Raised by the ML model on the IBM AML dataset · top 25 accounts per bank per day
                {summary.synced_at ? ` · synced ${new Date(String(summary.synced_at)).toLocaleString()}` : ''}
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <select value={simulation} onChange={e => setSimulation(e.target.value)}
                className="text-[11px] bg-white/[0.03] border border-white/[0.08] rounded-lg px-2 py-1 text-t2">
                {SIMULATIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <Badge label={`${total.toLocaleString()} ${filter === 'all' ? 'total' : 'match'}`} color={total ? 'amber' : 'gray'} />
            </div>
          </div>

          <div className="px-5 py-2 flex gap-1.5 border-b border-white/[0.04] overflow-x-auto">
            {FILTERS.map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={`px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all capitalize flex-shrink-0
                  ${filter === f ? 'bg-purple-500/15 border border-purple-500/25 text-purple-300' : 'text-t3 hover:text-t2 bg-white/[0.03] border border-white/[0.05]'}`}>
                {f}
              </button>
            ))}
          </div>

          <div className="divide-y divide-white/[0.04] max-h-[460px] overflow-y-auto">
            {loading ? (
              <div className="flex justify-center py-10">
                <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : error ? (
              <div className="py-12 text-center text-sm text-red-400">{error}</div>
            ) : !ready ? (
              <div className="py-12 px-6 text-center">
                <div className="text-2xl mb-2">⏳</div>
                <p className="text-sm text-t2">No ML alerts have been synced yet.</p>
                <p className="text-xs text-t3 mt-1 font-mono">python -m src.data.sync_ml_alerts</p>
              </div>
            ) : cases.length === 0 ? (
              <div className="py-12 text-center">
                <div className="text-2xl mb-2">🔎</div>
                <p className="text-sm text-t3">No alerts match the current filter</p>
              </div>
            ) : (
              <>
                {cases.map((c, i) => (
                  <motion.div
                    key={c.id}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: Math.min(i, 20) * 0.02 }}
                    onClick={() => setSelected(c)}
                    className={`px-5 py-3.5 cursor-pointer transition-colors ${selected?.id === c.id ? 'bg-purple-500/[0.08]' : 'hover:bg-white/[0.02]'}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-mono text-t2 truncate">{c.account_id}</span>
                          <Badge label={c.severity} color={sev(c.severity)} dot />
                        </div>
                        <div className="text-sm font-medium text-t1 capitalize mb-0.5">
                          {titleCase(c.predicted_pattern)} <span className="text-[10px] text-t3 normal-case font-normal">(predicted)</span>
                        </div>
                        <div className="text-xs text-t2 truncate">{c.description}</div>
                        <div className="text-xs text-t3 mt-1.5 flex gap-3 flex-wrap">
                          <span>{c.simulation_name}</span>
                          <span>{fmtDate(c.date_range_start)}</span>
                          <span>#{c.rank_in_day} that day</span>
                          <span>{c.transaction_count} txn</span>
                          <span className="tabular-nums">score {c.risk_score?.toFixed(3)}</span>
                        </div>
                      </div>
                      <Badge label={c.status} color={statusColor(c.status)} />
                    </div>
                  </motion.div>
                ))}
                {cases.length < total && (
                  <div className="py-3 text-center">
                    <button onClick={loadMore} disabled={loadingMore}
                      className="text-xs text-purple-300 hover:text-purple-200 disabled:opacity-50">
                      {loadingMore ? 'Loading…' : `Load more (${(total - cases.length).toLocaleString()} left)`}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </GlassCard>

        {/* Detail panel */}
        <GlassCard animate={false} className="col-span-2">
          <div className="px-5 py-4 border-b border-white/[0.06]">
            <h3 className="text-sm font-semibold text-t1">Alert Detail</h3>
          </div>
          <div className="p-5 max-h-[560px] overflow-y-auto">
            <AnimatePresence mode="wait">
              {selected ? (
                <motion.div key={selected.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-mono text-purple-400 break-all">{selected.account_id}</span>
                    <Badge label={selected.severity} color={sev(selected.severity)} dot />
                  </div>

                  <div>
                    <div className="text-[10px] text-t3 uppercase tracking-widest mb-1">Risk score</div>
                    <div className="flex items-center gap-3">
                      <div className="flex-1 h-2 rounded-full bg-white/[0.05] overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-amber-500 to-red-500" style={{ width: `${(selected.risk_score ?? 0) * 100}%` }} />
                      </div>
                      <span className="text-sm font-semibold tabular-nums text-t1">{selected.risk_score?.toFixed(3)}</span>
                    </div>
                    <p className="text-[10px] text-t3 mt-1">
                      The model's estimated chance that this account's riskiest payment that day is laundering.
                      Ranked #{selected.rank_in_day} in {selected.simulation_name} on {fmtDate(selected.date_range_start)}.
                    </p>
                  </div>

                  {/* Why */}
                  <div>
                    <p className="text-[10px] text-t3 uppercase tracking-widest mb-2">Why the model flagged it</p>
                    <div className="space-y-1.5">
                      {(selected.reasons ?? []).length === 0 ? (
                        <p className="text-xs text-t3">No reasons recorded.</p>
                      ) : selected.reasons!.map((r, i) => (
                        <div key={i} className="flex gap-2 text-xs text-t2 bg-white/[0.02] rounded-lg px-3 py-2 border border-white/[0.05]">
                          <span className="text-amber-400/70 shrink-0 tabular-nums">{i + 1}.</span>
                          <span className="leading-relaxed">{r.text}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Pattern hint */}
                  <div className="rounded-lg px-3 py-2.5 border border-blue-500/20 bg-blue-500/[0.05]">
                    <div className="text-xs text-t1">
                      Predicted pattern: <span className="font-semibold capitalize">{titleCase(selected.predicted_pattern)}</span>
                      {selected.pattern_probability != null && (
                        <span className="text-t3"> ({Math.round(selected.pattern_probability * 100)}% confidence)</span>
                      )}
                    </div>
                    <p className="text-[10px] text-t3 mt-1">A hint, not a finding: on past alerts this guess was right about half the time.</p>
                  </div>

                  {/* Facts */}
                  <div>
                    {[
                      { label: 'Owner', value: selected.owner_name ?? '—' },
                      { label: 'Bank', value: selected.bank_name ?? '—' },
                      { label: 'Simulated bank', value: selected.simulation_name ?? '—' },
                      { label: 'Payments that day', value: String(selected.transaction_count ?? '—') },
                      { label: 'Riskiest payment', value: `${fmtUsd(selected.top_transaction?.amount_usd)} ${selected.top_transaction?.payment_format ?? ''}` },
                      { label: 'Paid at', value: selected.top_transaction?.timestamp?.slice(0, 16) ?? '—' },
                      { label: 'From', value: selected.top_transaction?.from_account ?? '—' },
                      { label: 'To', value: selected.top_transaction?.to_account ?? '—' },
                      { label: 'Status', value: selected.status },
                      { label: 'Analyst', value: selected.analyst_id ?? 'Unassigned' },
                      { label: 'Model', value: selected.model_version ?? '—' },
                    ].map(row => (
                      <div key={row.label} className="flex justify-between items-start gap-3 py-2 border-b border-white/[0.04] text-xs">
                        <span className="text-t3 font-medium shrink-0">{row.label}</span>
                        <span className="text-t1 text-right font-mono text-[11px] break-all">{row.value}</span>
                      </div>
                    ))}
                  </div>

                  <p className="text-[10px] text-t3 leading-relaxed">
                    The model decides what to flag; a person decides what it means. The AI investigation (evidence,
                    typology and SAR draft) is not connected to this screen yet.
                  </p>
                </motion.div>
              ) : (
                <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="text-3xl mb-3">🔎</div>
                  <p className="text-sm text-t3">Select an alert to see why it was flagged</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
