import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { amlApi } from '@/services/api';
import GlassCard from '@/components/common/GlassCard';
import Badge from '@/components/common/Badge';
import type { AMLCase } from '@/types/banking';
import type { CustomerSummary } from '@/types';

const fmtMoney = (cents: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(cents / 100);

const sev = (s: string): 'red' | 'amber' | 'blue' | 'green' | 'gray' =>
  ({ critical: 'red', high: 'amber', medium: 'blue', low: 'green' } as Record<string, 'red' | 'amber' | 'blue' | 'green'>)[s] ?? 'gray';

const statusColor = (s: string): 'amber' | 'blue' | 'green' | 'red' | 'gray' =>
  ({ open: 'amber', reviewing: 'blue', resolved: 'green', escalated: 'red' } as Record<string, 'amber' | 'blue' | 'green' | 'red' | 'gray'>)[s] ?? 'gray';

interface AMLCenterProps {
  customer?: CustomerSummary | null;
}

export default function AMLCenter({ customer }: AMLCenterProps) {
  const [cases, setCases] = useState<AMLCase[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [dbTotal, setDbTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<AMLCase | null>(null);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    setLoading(true);
    setSelected(null);
    amlApi.cases({ customer_id: customer?.customer_id, limit: customer?.customer_id ? 50 : 200 }).then(res => {
      setCases(res.cases);
      setSummary(res.summary ?? {});
      setDbTotal(res.total ?? res.cases.length);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [customer?.customer_id]);

  const visible = filter === 'all' ? cases : cases.filter(c => c.severity === filter || c.status === filter);

  return (
    <div className="space-y-4">
      {/* Customer context banner */}
      {customer && (
        <GlassCard animate={false} className="px-4 py-3 border-l-2 border-amber-500/40 flex items-center gap-3">
          <span className="text-sm">🔎</span>
          <div>
            <span className="text-xs font-medium text-t1">{customer.name}</span>
            <span className="text-[10px] text-t3 ml-2">· {customer.customer_id}</span>
          </div>
          <span className="ml-auto text-[10px] text-amber-400">{cases.length} AML cases</span>
        </GlassCard>
      )}

      {/* Stat row */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { key: 'critical', label: 'Critical',  color: 'red',    tooltip: 'Cases with risk score ≥ 0.85 — require immediate escalation to Compliance' },
          { key: 'high',     label: 'High',      color: 'amber',  tooltip: 'Risk score 0.70–0.84 — enhanced monitoring and manager sign-off required' },
          { key: 'open',     label: 'Open',      color: 'blue',   tooltip: 'Cases currently under active investigation and not yet resolved' },
          { key: 'sar_filed',label: 'SAR Filed', color: 'purple', tooltip: 'Suspicious Activity Reports filed with FinCEN — regulatory submissions' },
        ].map((item, i) => (
          <GlassCard key={item.key} delay={i * 0.06} className="p-4 cursor-pointer group relative" onClick={() => setFilter(filter === item.key ? 'all' : item.key)}>
            <div className={`text-2xl font-bold tabular-nums text-${item.color}-400 mb-0.5`}>
              {summary[item.key] ?? 0}
            </div>
            <div className="text-xs text-t3 uppercase tracking-wider">{item.label}</div>
            <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block w-48 px-2 py-1.5 rounded-lg bg-gray-900 border border-white/[0.08] text-[10px] text-t2 z-10 shadow-lg">
              {item.tooltip}
            </div>
          </GlassCard>
        ))}
      </div>

      <div className="grid grid-cols-5 gap-4">
        {/* Case list */}
        <GlassCard animate={false} className="col-span-3 overflow-hidden">
          <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-t1">AML Cases</h2>
              <p className="text-xs text-t3">
                Anti-Money Laundering monitoring — real fraud_alerts database
                {!customer && dbTotal > cases.length && (
                  <span className="ml-1 text-amber-400/70">· showing {cases.length} of {dbTotal}</span>
                )}
              </p>
            </div>
            <Badge
              label={filter === 'all' ? `${dbTotal} total` : `${visible.length} of ${dbTotal}`}
              color={dbTotal ? 'amber' : 'gray'}
            />
          </div>

          {/* Filter chips */}
          <div className="px-5 py-2 flex gap-1.5 border-b border-white/[0.04]">
            {['all', 'open', 'reviewing', 'resolved', 'critical', 'high', 'medium'].map(f => (
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
            ) : visible.length === 0 ? (
              <div className="py-12 text-center">
                <div className="text-2xl mb-2">🔎</div>
                <p className="text-sm text-t3">No cases match the current filter</p>
              </div>
            ) : visible.map((c, i) => (
              <motion.div
                key={c.id}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                onClick={() => setSelected(c)}
                className={`px-5 py-4 cursor-pointer transition-colors ${selected?.id === c.id ? 'bg-purple-500/[0.08]' : 'hover:bg-white/[0.02]'}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono text-t3">{c.id}</span>
                      <Badge label={c.severity} color={sev(c.severity)} dot />
                    </div>
                    <div className="text-sm font-medium text-t1 capitalize mb-0.5">{c.case_type.replace(/_/g, ' ')}</div>
                    <div className="text-xs text-t2 truncate max-w-xs">{c.description}</div>
                    <div className="text-xs text-t3 mt-1.5 flex gap-3 flex-wrap">
                      <span className="font-mono">{c.customer_id}</span>
                      {(c.total_amount_cents ?? 0) > 0 && (
                        <span className="text-green-400/70">{fmtMoney(c.total_amount_cents)}</span>
                      )}
                      <span>{c.transaction_count ?? 1} txn</span>
                      <span>{c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}</span>
                      {(c as unknown as { location?: string }).location && (
                        <span className="text-blue-400/70">📍 {(c as unknown as { location?: string }).location}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                    <Badge label={c.status} color={statusColor(c.status)} />
                    {c.sar_filed && <Badge label="SAR Filed" color="purple" />}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </GlassCard>

        {/* Detail panel */}
        <GlassCard animate={false} className="col-span-2">
          <div className="px-5 py-4 border-b border-white/[0.06]">
            <h3 className="text-sm font-semibold text-t1">Case Detail</h3>
          </div>
          <div className="p-5">
            <AnimatePresence mode="wait">
              {selected ? (
                <motion.div key={selected.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-purple-400">{selected.id}</span>
                    <Badge label={selected.severity} color={sev(selected.severity)} dot />
                  </div>
                  <div>
                    <div className="text-base font-semibold text-t1 capitalize mb-1">{selected.case_type.replace(/_/g, ' ')}</div>
                    <p className="text-xs text-t2 leading-relaxed">{selected.description}</p>
                  </div>
                  {[
                    { label: 'Customer',      value: selected.customer_id },
                    { label: 'Total Amount',  value: (selected.total_amount_cents ?? 0) > 0 ? fmtMoney(selected.total_amount_cents) : '—' },
                    { label: 'Transactions',  value: String(selected.transaction_count ?? 1) },
                    { label: 'Date',          value: selected.date_range_start ?? '—' },
                    { label: 'Status',        value: selected.status },
                    { label: 'Analyst',       value: selected.analyst_id ?? 'Unassigned' },
                    { label: 'SAR Reference', value: selected.sar_reference ?? (selected.sar_filed ? 'Filed' : 'Not filed') },
                    { label: 'Location',      value: (selected as unknown as { location?: string }).location ?? '—' },
                    { label: 'Merchant',      value: (selected as unknown as { merchant?: string }).merchant ?? '—' },
                    { label: 'Category',      value: (selected as unknown as { category?: string }).category ?? '—' },
                    { label: 'Detected',      value: selected.created_at ? new Date(selected.created_at).toLocaleString() : '—' },
                  ].map(row => (
                    <div key={row.label} className="flex justify-between items-start py-2 border-b border-white/[0.04] text-xs">
                      <span className="text-t3 font-medium">{row.label}</span>
                      <span className="text-t1 text-right max-w-[60%]">{row.value}</span>
                    </div>
                  ))}
                </motion.div>
              ) : (
                <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="text-3xl mb-3">🔎</div>
                  <p className="text-sm text-t3">Select a case to view details</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
