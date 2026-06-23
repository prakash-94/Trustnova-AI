import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import GlassCard from '@/components/common/GlassCard';
import Badge from '@/components/common/Badge';
import { complianceApi, type ComplianceComplaint, type ComplianceStats } from '@/services/api';

// ── Static reference data (doesn't change in banking operations) ──────────────
const REGULATIONS = [
  { code: 'BSA/AML',   title: 'Bank Secrecy Act / AML',          status: 'compliant',        next_review: '2026-08-01' },
  { code: 'KYC/CDD',   title: 'Know Your Customer / CDD',         status: 'compliant',        next_review: '2026-07-15' },
  { code: 'OFAC',      title: 'OFAC Sanctions Screening',         status: 'action_required',  next_review: '2026-06-20' },
  { code: 'TILA',      title: 'Truth in Lending Act',             status: 'compliant',        next_review: '2026-09-01' },
  { code: 'HMDA',      title: 'Home Mortgage Disclosure Act',     status: 'under_review',     next_review: '2026-06-10' },
  { code: 'CRA',       title: 'Community Reinvestment Act',       status: 'compliant',        next_review: '2026-08-15' },
  { code: 'GDPR/CCPA', title: 'Data Privacy Compliance',         status: 'compliant',        next_review: '2026-10-01' },
  { code: 'FFIEC',     title: 'FFIEC Cybersecurity Framework',   status: 'under_review',     next_review: '2026-06-15' },
];

const AUDITS = [
  { id: 'AUD-2026-001', type: 'Internal',   scope: 'AML Program Review',       status: 'completed',   date: '2026-04-30', findings: 2, critical: 0 },
  { id: 'AUD-2026-002', type: 'External',   scope: 'Annual SOX Audit',         status: 'in_progress', date: '2026-06-01', findings: 0, critical: 0 },
  { id: 'AUD-2026-003', type: 'Regulatory', scope: 'OCC Safety & Soundness',   status: 'scheduled',   date: '2026-07-15', findings: 0, critical: 0 },
  { id: 'AUD-2025-004', type: 'Internal',   scope: 'Loan Portfolio Review',    status: 'completed',   date: '2025-12-31', findings: 5, critical: 1 },
];

const TRAINING = [
  { course: 'BSA/AML Annual Certification', completion: 94, due: '2026-06-30', mandatory: true },
  { course: 'Fraud Awareness Training',      completion: 87, due: '2026-07-31', mandatory: true },
  { course: 'Data Privacy & GDPR',          completion: 76, due: '2026-08-31', mandatory: true },
  { course: 'OFAC Sanctions Screening',      completion: 98, due: '2026-05-31', mandatory: true },
];

// ── Helpers ───────────────────────────────────────────────────────────────────
const statusColor = (s: string): 'green' | 'amber' | 'red' | 'blue' | 'gray' =>
  ({
    compliant: 'green', under_review: 'amber', action_required: 'red',
    in_progress: 'blue', completed: 'green', scheduled: 'gray',
    Resolved: 'green', 'In Review': 'blue', Open: 'amber',
  } as Record<string, 'green' | 'amber' | 'red' | 'blue' | 'gray'>)[s] ?? 'gray';

const sentimentLabel = (s: number) => s >= -0.3 ? 'Neutral' : s >= -0.6 ? 'Negative' : 'Very Negative';
const sentimentColor = (s: number) => s >= -0.3 ? 'text-green-400' : s >= -0.6 ? 'text-amber-400' : 'text-red-400';

type ComplaintFilter = 'all' | 'open' | 'in_review' | 'resolved';
const FILTERS: { key: ComplaintFilter; label: string }[] = [
  { key: 'all',       label: 'All'       },
  { key: 'open',      label: 'Open'      },
  { key: 'in_review', label: 'In Review' },
  { key: 'resolved',  label: 'Resolved'  },
];

const PAGE_SIZE = 15;

export default function ComplianceDashboard() {
  const [stats, setStats]         = useState<ComplianceStats | null>(null);
  const [complaints, setComplaints] = useState<ComplianceComplaint[]>([]);
  const [total, setTotal]         = useState(0);
  const [filter, setFilter]       = useState<ComplaintFilter>('all');
  const [page, setPage]           = useState(0);
  const [expanded, setExpanded]   = useState<string | null>(null);
  const [loading, setLoading]     = useState(true);
  const [cLoading, setCLoading]   = useState(true);

  // Load KPI stats once
  useEffect(() => {
    complianceApi.stats()
      .then(setStats)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Reload complaints when filter or page changes
  useEffect(() => {
    setCLoading(true);
    setExpanded(null);
    complianceApi.complaints({ status: filter, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then(r => { setComplaints(r.complaints); setTotal(r.total); })
      .catch(() => setComplaints([]))
      .finally(() => setCLoading(false));
  }, [filter, page]);

  // Reset page when filter changes
  const handleFilter = (f: ComplaintFilter) => { setFilter(f); setPage(0); };

  const counts = stats?.complaint_counts;
  const filterCount: Record<ComplaintFilter, number> = {
    all:       counts?.total    ?? 0,
    open:      counts?.open     ?? 0,
    in_review: counts?.in_review ?? 0,
    resolved:  counts?.resolved ?? 0,
  };

  const compliant   = REGULATIONS.filter(r => r.status === 'compliant').length;
  const actionItems = REGULATIONS.filter(r => r.status === 'action_required').length;
  const inReview    = REGULATIONS.filter(r => r.status === 'under_review').length;

  return (
    <div className="space-y-4">
      {/* KPIs — live from DB */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Compliant Controls', value: loading ? '…' : `${compliant}/${REGULATIONS.length}`, color: 'green'  },
          { label: 'Action Required',    value: loading ? '…' : actionItems,                          color: actionItems > 0 ? 'red' : 'green' },
          { label: 'Open Complaints',    value: loading ? '…' : (counts?.open ?? '—'),                color: (counts?.open ?? 0) > 0 ? 'red' : 'green' },
          { label: 'Total Complaints',   value: loading ? '…' : (counts?.total ?? '—'),               color: 'blue'   },
        ].map((m, i) => (
          <GlassCard key={m.label} delay={i * 0.06} className="p-4">
            <div className={`text-2xl font-bold tabular-nums text-${m.color}-400 mb-0.5`}>{m.value}</div>
            <div className="text-xs text-t3 uppercase tracking-wider">{m.label}</div>
          </GlassCard>
        ))}
      </div>

      {/* Complaints Table — live from DB */}
      <GlassCard animate={false} className="overflow-hidden">
        <div className="px-5 py-4 border-b border-white/[0.06]">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold text-t1">Customer Complaints Register</h2>
              <p className="text-xs text-t3">
                Live from banking.db — {counts?.total?.toLocaleString() ?? '…'} complaints total
              </p>
            </div>
            <div className="text-xs text-t3">{filterCount[filter].toLocaleString()} matching</div>
          </div>
          <div className="flex gap-1.5">
            {FILTERS.map(f => (
              <button key={f.key} onClick={() => handleFilter(f.key)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all
                  ${filter === f.key
                    ? 'bg-white/[0.08] border border-white/[0.12] text-t1'
                    : 'text-t3 hover:text-t2 hover:bg-white/[0.04]'}`}>
                {f.label} <span className="opacity-60">({filterCount[f.key].toLocaleString()})</span>
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          {cLoading ? (
            <div className="flex items-center gap-2 px-5 py-6 text-xs text-t3">
              <div className="w-3 h-3 border border-purple-500 border-t-transparent rounded-full animate-spin" />
              Loading complaints…
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  {['ID', 'Customer', 'Date', 'Category', 'Complaint', 'Sentiment', 'Status', ''].map(h => (
                    <th key={h} className="px-4 py-2.5 text-left text-[10px] text-t3 uppercase tracking-wider font-medium whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {complaints.map(c => (
                  <>
                    <tr key={c.id} className="hover:bg-white/[0.02] transition-colors cursor-pointer"
                      onClick={() => setExpanded(expanded === c.id ? null : c.id)}>
                      <td className="px-4 py-3 font-mono text-purple-400 whitespace-nowrap">
                        {c.id.slice(0, 11)}
                      </td>
                      <td className="px-4 py-3 font-mono text-t3 text-[10px]">
                        {c.customer_id.slice(0, 8)}
                      </td>
                      <td className="px-4 py-3 text-t3 whitespace-nowrap">{c.timestamp.slice(0, 10)}</td>
                      <td className="px-4 py-3">
                        <span className="px-1.5 py-0.5 rounded bg-white/[0.06] text-t2 whitespace-nowrap">{c.category}</span>
                      </td>
                      <td className="px-4 py-3 text-t2 max-w-[220px]">
                        <span className="truncate block">{c.description}</span>
                      </td>
                      <td className={`px-4 py-3 font-medium ${sentimentColor(c.sentiment)}`}>
                        {sentimentLabel(c.sentiment)}
                      </td>
                      <td className="px-4 py-3">
                        <Badge label={c.status} color={statusColor(c.status)} dot={c.status === 'Open'} />
                      </td>
                      <td className="px-4 py-3 text-t3 text-center">
                        {expanded === c.id ? '▲' : '▼'}
                      </td>
                    </tr>
                    {expanded === c.id && (
                      <tr key={`${c.id}-expand`}>
                        <td colSpan={8} className="px-4 pb-3">
                          <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="ml-4 p-3 rounded-xl bg-white/[0.03] border border-white/[0.06] space-y-3"
                          >
                            <div className="grid grid-cols-2 gap-3">
                              <div>
                                <span className="text-[10px] text-t3 uppercase tracking-wider">Full Complaint</span>
                                <p className="text-xs text-t2 mt-0.5 leading-relaxed">{c.description}</p>
                              </div>
                              {c.resolution && (
                                <div>
                                  <span className="text-[10px] text-t3 uppercase tracking-wider">Resolution</span>
                                  <p className="text-xs text-green-300 mt-0.5 leading-relaxed">{c.resolution}</p>
                                </div>
                              )}
                            </div>
                            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[10px] text-t3 pt-2 border-t border-white/[0.05]">
                              <span>Reference: <span className="font-mono text-purple-400/80">{c.id}</span></span>
                              <span>Customer: <span className="font-mono text-t2">{c.customer_id}</span></span>
                              <span>Category: <span className="text-t2">{c.category}</span></span>
                              <span>Raised by: <span className="text-t2">{c.raised_by}</span></span>
                              <span>Sentiment: <span className={sentimentColor(c.sentiment)}>{c.sentiment.toFixed(2)}</span></span>
                              <span>Logged: <span className="font-mono text-t2">{c.timestamp}</span></span>
                            </div>
                          </motion.div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {!cLoading && total > PAGE_SIZE && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-white/[0.06]">
            <span className="text-[10px] text-t3">
              {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total.toLocaleString()}
            </span>
            <div className="flex gap-2">
              <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                className="px-3 py-1 text-xs rounded-lg bg-white/[0.04] border border-white/[0.08] text-t2
                           hover:bg-white/[0.08] disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                ← Prev
              </button>
              <button onClick={() => setPage(p => p + 1)} disabled={(page + 1) * PAGE_SIZE >= total}
                className="px-3 py-1 text-xs rounded-lg bg-white/[0.04] border border-white/[0.08] text-t2
                           hover:bg-white/[0.08] disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                Next →
              </button>
            </div>
          </div>
        )}
      </GlassCard>

      <div className="grid grid-cols-2 gap-4">
        {/* Regulatory Controls */}
        <GlassCard animate={false} className="overflow-hidden">
          <div className="px-5 py-4 border-b border-white/[0.06]">
            <h2 className="text-sm font-semibold text-t1">Regulatory Controls</h2>
            <p className="text-xs text-t3">
              {compliant}/{REGULATIONS.length} compliant · {actionItems} action required · {inReview} under review
            </p>
          </div>
          <div className="divide-y divide-white/[0.04]">
            {REGULATIONS.map((reg, i) => (
              <motion.div key={reg.code} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}
                className="px-5 py-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-mono font-semibold text-purple-400">{reg.code}</span>
                    <Badge label={reg.status.replace('_', ' ')} color={statusColor(reg.status)} />
                  </div>
                  <div className="text-[11px] text-t3">{reg.title}</div>
                </div>
                <div className="text-right text-[10px] text-t3">
                  <div>Next: {reg.next_review}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </GlassCard>

        <div className="space-y-4">
          {/* Audit Schedule */}
          <GlassCard animate={false} className="overflow-hidden">
            <div className="px-5 py-4 border-b border-white/[0.06]">
              <h2 className="text-sm font-semibold text-t1">Audit Schedule</h2>
            </div>
            <div className="divide-y divide-white/[0.04]">
              {AUDITS.map((a, i) => (
                <motion.div key={a.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.05 }}
                  className="px-5 py-3">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-t3">{a.id}</span>
                      <Badge label={a.type} color="gray" />
                    </div>
                    <Badge label={a.status.replace('_', ' ')} color={statusColor(a.status)} />
                  </div>
                  <div className="text-xs text-t2">{a.scope}</div>
                  <div className="flex gap-3 text-[10px] text-t3 mt-1">
                    <span>{a.date}</span>
                    {a.findings > 0 && (
                      <span className={a.critical > 0 ? 'text-red-400' : 'text-amber-400'}>
                        {a.findings} finding{a.findings !== 1 ? 's' : ''}{a.critical > 0 ? ` (${a.critical} critical)` : ''}
                      </span>
                    )}
                  </div>
                </motion.div>
              ))}
            </div>
          </GlassCard>

          {/* Category Breakdown — live from DB */}
          <GlassCard animate={false} className="p-5">
            <h2 className="text-sm font-semibold text-t1 mb-4">Complaint Categories</h2>
            {loading ? (
              <div className="text-xs text-t3">Loading…</div>
            ) : (
              <div className="space-y-3">
                {(stats?.categories ?? []).map(cat => {
                  const pct = counts?.total ? Math.round((cat.count / counts.total) * 100) : 0;
                  return (
                    <div key={cat.name}>
                      <div className="flex justify-between text-xs mb-1.5">
                        <span className="text-t2">{cat.name}</span>
                        <span className="text-t3">{cat.count.toLocaleString()} ({pct}%)</span>
                      </div>
                      <div className="w-full h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${pct}%` }}
                          transition={{ duration: 0.8, ease: 'easeOut' }}
                          className="h-full rounded-full bg-purple-400"
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </GlassCard>

          {/* Mandatory Training */}
          <GlassCard animate={false} className="p-5">
            <h2 className="text-sm font-semibold text-t1 mb-4">Mandatory Training</h2>
            <div className="space-y-4">
              {TRAINING.map(t => (
                <div key={t.course}>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-t2">{t.course}</span>
                    <span className={t.completion >= 90 ? 'text-green-400' : 'text-amber-400'}>{t.completion}%</span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${t.completion}%` }}
                      transition={{ duration: 0.8, ease: 'easeOut' }}
                      className={`h-full rounded-full ${t.completion >= 90 ? 'bg-green-400' : 'bg-amber-400'}`}
                    />
                  </div>
                  <div className="text-[10px] text-t3 mt-0.5">Due: {t.due}</div>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}