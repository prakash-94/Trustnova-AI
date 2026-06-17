/**
 * BankLoansCenter — Bank-wide Loan Operations Module
 *
 * ARCHITECTURE RULE: This component shows ALL loans across the institution.
 * It is NOT filtered by a selected customer.  That separation is intentional:
 *
 *   Customer 360 → Loans tab   = one customer's loans only
 *   BankLoansCenter (this file) = BANK-WIDE loan portfolio management
 *
 * Use-case:
 *   A Loan Officer opens "Loans" in the Bank Operations sidebar.
 *   He sees the bank holds 1,594 total loans.
 *   He clicks the "Personal" tab → 400+ personal loans listed.
 *   He clicks the "Pending" status pill → narrows to loans awaiting decision.
 *   He can see: approval rate, avg amount, outstanding balance, delinquency count.
 *
 * Loan Type Tabs (5 — covering all DB loan_type values):
 *   Student (education) | Home/Mortgage (home) | Auto | Personal | Business
 *
 * Status Categories (8 user-facing labels mapped to DB values):
 *   Received → pending        | Under Review → reviewing
 *   Approved → approved       | Disbursed    → funded
 *   Rejected → declined       | Closed       → defaulted/closed
 *
 * Data flow:
 *   1. On mount           → loansApi.portfolio() → global KPI cards
 *   2. On tab/status change → loansApi.list(type, status) → table rows
 *   3. Approval/rejection rates computed client-side from portfolio stats
 */

import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';
import { loansApi } from '@/services/api';
import GlassCard from '@/components/common/GlassCard';
import Badge from '@/components/common/Badge';
import LoanDetailPanel from './LoanDetailPanel';
import type { Loan } from '@/types/banking';

// ── Constants ────────────────────────────────────────────────────────────────

const PAGE_SIZE = 50;

/**
 * Loan type tabs.
 * `dbType` is the loan_type value stored in the DB.
 * 'all' has no filter.
 */
const LOAN_TYPES = [
  { id: 'all',       label: 'All Loans',     icon: '📋', dbType: null },
  { id: 'education', label: 'Student',        icon: '🎓', dbType: 'education' },
  { id: 'home',      label: 'Home/Mortgage',  icon: '🏠', dbType: 'home' },
  { id: 'auto',      label: 'Auto',           icon: '🚗', dbType: 'auto' },
  { id: 'personal',  label: 'Personal',       icon: '👤', dbType: 'personal' },
  { id: 'business',  label: 'Business',       icon: '🏢', dbType: 'business' },
] as const;

type LoanTypeId = (typeof LOAN_TYPES)[number]['id'];

/**
 * Status filter pills.
 * Mapping from user-facing label (per business spec) to DB status value.
 * 'all' = no status filter.
 */
const STATUS_FILTERS = [
  { id: 'all',       label: 'All',               icon: '📋', dbStatus: null,        color: 'gray' },
  { id: 'pending',   label: 'Received/Pending',   icon: '📥', dbStatus: 'pending',   color: 'blue' },
  { id: 'approved',  label: 'Approved',            icon: '✅', dbStatus: 'approved',  color: 'green' },
  { id: 'active',    label: 'Disbursed/Active',    icon: '💸', dbStatus: 'active',    color: 'cyan' },
  { id: 'rejected',  label: 'Rejected',            icon: '❌', dbStatus: 'rejected',  color: 'red' },
  { id: 'completed', label: 'Closed/Completed',    icon: '🔒', dbStatus: 'completed', color: 'amber' },
] as const;

type StatusId = (typeof STATUS_FILTERS)[number]['id'];

// ── Formatters ───────────────────────────────────────────────────────────────

const fmt$ = (cents?: number | null) =>
  cents != null
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(cents / 100)
    : '—';

const fmtPct = (n: number, d: number) => (d > 0 ? `${((n / d) * 100).toFixed(1)}%` : '0%');

// ── Portfolio KPI card ────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, icon, accent }: {
  label: string; value: string; sub?: string; icon: string; accent: string;
}) {
  return (
    <GlassCard animate={false} className={clsx('p-4 border-t-2', accent)}>
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[10px] text-t3 uppercase tracking-wider mb-1">{label}</div>
          <div className="text-xl font-bold text-t1 tabular-nums">{value}</div>
          {sub && <div className="text-[10px] text-t3 mt-0.5">{sub}</div>}
        </div>
        <span className="text-xl opacity-60">{icon}</span>
      </div>
    </GlassCard>
  );
}

// ── Approval rate chart ───────────────────────────────────────────────────────
/**
 * ApprovalChart shows approval vs rejection rates as coloured progress bars.
 *
 * Input:  byStatus = { "approved": 320, "funded": 411, "declined": 284, ... }
 * Output: Two bars + percentage labels for approval and rejection.
 */
function ApprovalChart({
  byStatus,
}: {
  byStatus: Record<string, number>;
}) {
  const total = Object.values(byStatus).reduce((a, b) => a + b, 0) || 1;
  const approved = (byStatus['approved'] ?? 0) + (byStatus['active'] ?? 0);
  const declined = byStatus['rejected'] ?? 0;
  const pending  = byStatus['pending'] ?? 0;

  const segments = [
    { label: 'Approved/Disbursed', count: approved, color: 'bg-green-400', pct: (approved / total) * 100 },
    { label: 'Pending/Review',     count: pending,  color: 'bg-amber-400', pct: (pending  / total) * 100 },
    { label: 'Rejected',           count: declined, color: 'bg-red-400',   pct: (declined / total) * 100 },
  ];

  return (
    <div className="space-y-2.5">
      {segments.map(seg => (
        <div key={seg.label}>
          <div className="flex justify-between text-[10px] mb-1">
            <span className="text-t3">{seg.label}</span>
            <span className="text-t2 tabular-nums">{seg.count.toLocaleString()} ({fmtPct(seg.count, total)})</span>
          </div>
          <div className="w-full h-2 rounded-full bg-white/[0.06]">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${seg.pct}%` }}
              transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
              className={clsx('h-full rounded-full', seg.color)}
            />
          </div>
        </div>
      ))}
      {/* Stacked visual bar */}
      <div className="flex h-3 rounded-full overflow-hidden gap-0.5 mt-3">
        {segments.map(seg => (
          <motion.div
            key={seg.label}
            initial={{ flex: 0 }}
            animate={{ flex: seg.pct }}
            transition={{ duration: 0.6 }}
            className={clsx('h-full', seg.color, 'opacity-70')}
            title={`${seg.label}: ${fmtPct(seg.count, total)}`}
          />
        ))}
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function BankLoansCenter() {
  const [activeLoanType, setActiveLoanType] = useState<LoanTypeId>('all');
  const [activeStatus, setActiveStatus]     = useState<StatusId>('all');

  // Portfolio stats — global (KPI cards) and per-type (status pill counts)
  const [globalPortfolio, setGlobalPortfolio] = useState<Record<string, unknown> | null>(null);
  const [portfolio, setPortfolio]             = useState<Record<string, unknown> | null>(null);
  const [portfolioLoading, setPortfolioLoading] = useState(true);

  // Table data
  const [loans, setLoans] = useState<Loan[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage]   = useState(0);
  const [tableLoading, setTableLoading] = useState(false);

  // Loan detail panel
  const [selectedLoanId, setSelectedLoanId] = useState<string | null>(null);

  // ── Data fetching ──────────────────────────────────────────────────────────

  /** Load global portfolio stats once (KPI cards — always bank-wide). */
  useEffect(() => {
    loansApi.portfolio()
      .then(p => { setGlobalPortfolio(p); setPortfolio(p); })
      .catch(() => {})
      .finally(() => setPortfolioLoading(false));
  }, []);

  /**
   * Load loans table whenever loan type OR status filter changes.
   *
   * API call:  GET /loans?loan_type={dbType}&status={dbStatus}&limit=50&offset=0
   *
   * The type/status mapping is defined in LOAN_TYPES and STATUS_FILTERS arrays.
   * 'all' means the filter parameter is omitted entirely.
   */
  const loadLoans = useCallback(async () => {
    setTableLoading(true);
    try {
      const typeDef   = LOAN_TYPES.find(t => t.id === activeLoanType)!;
      const statusDef = STATUS_FILTERS.find(s => s.id === activeStatus)!;

      const res = await loansApi.list(
        statusDef.dbStatus ?? undefined,
        typeDef.dbType     ?? undefined,
      );
      setLoans(res.loans);
      setTotal(res.total);
    } catch {
      setLoans([]);
      setTotal(0);
    } finally {
      setTableLoading(false);
    }
  }, [activeLoanType, activeStatus, page]);

  useEffect(() => { loadLoans(); }, [loadLoans]);

  const handleTypeChange = (id: LoanTypeId) => {
    setActiveLoanType(id);
    setActiveStatus('all');
    setPage(0);
    const typeDef = LOAN_TYPES.find(t => t.id === id)!;
    loansApi.portfolio(typeDef.dbType ?? undefined)
      .then(p => setPortfolio(p))
      .catch(() => {});
  };

  const handleStatusChange = (id: StatusId) => {
    setActiveStatus(id);
    setPage(0);
  };

  // ── Derived ───────────────────────────────────────────────────────────────

  // byStatus changes when a loan type tab is selected (filtered counts for status pills)
  const byStatus   = (portfolio?.by_status       as Record<string, number>) ?? {};
  // byType and KPI totals always use global bank-wide stats
  const byType     = (globalPortfolio?.by_type   as Record<string, { count: number }>) ?? {};
  const totalLoans = (globalPortfolio?.total_loans as number) ?? 0;
  const delinquent = (globalPortfolio?.delinquent_count as number) ?? 0;

  const approvedCount = (byStatus['approved'] ?? 0) + (byStatus['active'] ?? 0);
  const declinedCount = byStatus['rejected'] ?? 0;
  const totalPages    = Math.ceil(total / PAGE_SIZE);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">

      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <GlassCard animate={false} className="px-5 py-4">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-t1">Loan Operations Center</h2>
            <p className="text-xs text-t3 mt-0.5">
              Bank-wide loan portfolio — {totalLoans.toLocaleString()} total loans
              across all loan types and origination stages
            </p>
          </div>
          <span className="text-2xl">📋</span>
        </div>
      </GlassCard>

      {/* ── KPI Cards ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-5 gap-3">
        <KpiCard
          label="Total Loans"
          value={portfolioLoading ? '…' : totalLoans.toLocaleString()}
          sub="all types, all statuses"
          icon="📋" accent="border-purple-500/40"
        />
        <KpiCard
          label="Approval Rate"
          value={portfolioLoading ? '…' : fmtPct(approvedCount, totalLoans)}
          sub={`${approvedCount.toLocaleString()} approved/funded`}
          icon="✅" accent="border-green-500/40"
        />
        <KpiCard
          label="Rejection Rate"
          value={portfolioLoading ? '…' : fmtPct(declinedCount, totalLoans)}
          sub={`${declinedCount.toLocaleString()} declined`}
          icon="❌" accent="border-red-500/40"
        />
        <KpiCard
          label="Delinquent Loans"
          value={portfolioLoading ? '…' : delinquent.toLocaleString()}
          sub={fmtPct(delinquent, totalLoans) + ' of portfolio'}
          icon="⚠" accent="border-amber-500/40"
        />
        <KpiCard
          label="Loan Types"
          value={portfolioLoading ? '…' : Object.keys(byType).length.toLocaleString()}
          sub="active product types"
          icon="🗂" accent="border-cyan-500/40"
        />
      </div>

      {/* ── Analytics: Approval rates + Type distribution ────────────────────── */}
      <div className="grid grid-cols-5 gap-4">

        {/* Approval/rejection rate bars (3/5) */}
        <GlassCard animate={false} className="col-span-3 p-4">
          <h3 className="text-xs font-semibold text-t1 mb-4">Portfolio Status Distribution</h3>
          {portfolioLoading ? (
            <div className="flex items-center justify-center h-20 text-xs text-t3">
              <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mr-2" />
              Loading…
            </div>
          ) : (
            <ApprovalChart byStatus={byStatus} />
          )}
        </GlassCard>

        {/* Per-type counts (2/5) */}
        <GlassCard animate={false} className="col-span-2 p-4">
          <h3 className="text-xs font-semibold text-t1 mb-3">By Loan Type</h3>
          <div className="space-y-2">
            {Object.entries(byType).map(([type, info]) => {
              const pct = totalLoans ? (info.count / totalLoans) * 100 : 0;
              return (
                <div key={type}>
                  <div className="flex justify-between text-[10px] mb-0.5">
                    <span className="text-t2 capitalize">{type}</span>
                    <span className="text-t3">{info.count}</span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-white/[0.06]">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                      transition={{ duration: 0.5 }}
                      className="h-full rounded-full bg-purple-400/60"
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </GlassCard>
      </div>

      {/* ── Loan type tabs ───────────────────────────────────────────────────── */}
      <GlassCard animate={false} className="px-4 py-2.5">
        <div className="flex gap-1 flex-wrap">
          {LOAN_TYPES.map(lt => {
            const count = lt.id === 'all' ? totalLoans : (byType[lt.dbType ?? '']?.count ?? 0);
            return (
              <button
                key={lt.id}
                onClick={() => handleTypeChange(lt.id)}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap',
                  activeLoanType === lt.id
                    ? 'bg-purple-500/15 border border-purple-500/25 text-purple-300'
                    : 'text-t3 hover:text-t2 hover:bg-white/[0.04]',
                )}
              >
                <span>{lt.icon}</span>
                <span>{lt.label}</span>
                <span className={clsx('text-[9px]', activeLoanType === lt.id ? 'text-purple-400' : 'text-t3')}>
                  {count.toLocaleString()}
                </span>
              </button>
            );
          })}
        </div>
      </GlassCard>

      {/* ── Status filter pills ──────────────────────────────────────────────── */}
      {/*
        These pills map user-facing terminology (business spec) to DB status values.
        "Received/Pending" → DB status = 'pending'
        "Under Review"     → DB status = 'reviewing'
        "Disbursed"        → DB status = 'funded'
        "Rejected"         → DB status = 'declined'
      */}
      <GlassCard animate={false} className="px-4 py-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] text-t3 uppercase tracking-wider mr-1">Status:</span>
          {STATUS_FILTERS.map(sf => {
            const statusCount = sf.id === 'all' ? total : (byStatus[sf.dbStatus ?? ''] ?? 0);
            return (
              <button
                key={sf.id}
                onClick={() => handleStatusChange(sf.id)}
                className={clsx(
                  'flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-medium border transition-all whitespace-nowrap',
                  activeStatus === sf.id
                    ? `border-${sf.color}-500/40 bg-${sf.color}-500/15 text-${sf.color}-300`
                    : 'border-white/[0.08] text-t3 hover:text-t2 hover:bg-white/[0.04]',
                )}
              >
                <span>{sf.icon}</span>
                <span>{sf.label}</span>
                {sf.id !== 'all' && (
                  <span className="ml-0.5 text-[8px] opacity-70">{statusCount}</span>
                )}
              </button>
            );
          })}
        </div>
      </GlassCard>

      {/* ── Loans Table ──────────────────────────────────────────────────────── */}
      {/*
        Shows ALL bank loans for the selected type and status.
        NOT filtered by customer — any loan across the bank may appear.

        Columns: Loan ID, Type, Purpose/Description, Requested Amount,
                 Outstanding, Rate, Term, DTI%, Credit Score, Status, Delinquent

        Input:  loans[] from loansApi.list(type, status)
        Output: Sortable table with status badges and delinquency flags.
      */}
      <GlassCard animate={false} className="overflow-hidden">
        <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
          <div>
            <h3 className="text-xs font-semibold text-t1">
              {LOAN_TYPES.find(lt => lt.id === activeLoanType)?.label} Loans
              {activeStatus !== 'all' && ` — ${STATUS_FILTERS.find(s => s.id === activeStatus)?.label}`}
            </h3>
            <p className="text-[10px] text-t3 mt-0.5">
              {total.toLocaleString()} loan{total !== 1 ? 's' : ''} found
            </p>
          </div>
          {tableLoading && (
            <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/[0.06]">
                {['Loan ID', 'Type', 'Purpose', 'Requested', 'Outstanding', 'Rate', 'Term', 'DTI', 'Credit', 'Status', 'Overdue'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] text-t3 uppercase tracking-wider font-medium whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <AnimatePresence mode="wait">
              {tableLoading ? (
                <tbody>
                  <tr>
                    <td colSpan={11} className="py-16 text-center text-xs text-t3">
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                        Loading loans…
                      </div>
                    </td>
                  </tr>
                </tbody>
              ) : (
                <motion.tbody
                  key={`${activeLoanType}-${activeStatus}-${page}`}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  className="divide-y divide-white/[0.04]"
                >
                  {loans.length === 0 ? (
                    <tr>
                      <td colSpan={11} className="py-16 text-center text-sm text-t3">
                        <div className="text-2xl mb-2">📋</div>
                        No loans found for this filter
                      </td>
                    </tr>
                  ) : (
                    loans.map(loan => (
                      <tr key={loan.id}
                        className={clsx('hover:bg-white/[0.02] transition-colors', loan.is_delinquent && 'bg-red-500/[0.03]')}>
                        <td className="px-4 py-2.5">
                          <button
                            onClick={() => setSelectedLoanId(loan.id)}
                            className="font-mono text-purple-400 text-[10px] hover:text-purple-300 hover:underline transition-colors text-left"
                          >
                            {loan.id}
                          </button>
                        </td>
                        <td className="px-4 py-2.5 capitalize text-t2">{loan.loan_type.replace(/_/g, ' ')}</td>
                        <td className="px-4 py-2.5 text-t3 max-w-[140px] truncate">{loan.description ?? loan.purpose ?? '—'}</td>
                        <td className="px-4 py-2.5 text-t1 font-medium tabular-nums whitespace-nowrap">
                          {fmt$(loan.requested_amount_cents)}
                        </td>
                        <td className="px-4 py-2.5 text-t2 tabular-nums whitespace-nowrap">
                          {fmt$(loan.outstanding_balance_cents)}
                        </td>
                        <td className="px-4 py-2.5 text-t3 tabular-nums">
                          {loan.interest_rate != null ? `${loan.interest_rate}%` : '—'}
                        </td>
                        <td className="px-4 py-2.5 text-t3 tabular-nums whitespace-nowrap">
                          {loan.term_months ? `${loan.term_months}mo` : '—'}
                        </td>
                        <td className="px-4 py-2.5 tabular-nums">
                          <span className={clsx(loan.dti_ratio && loan.dti_ratio > 0.43 ? 'text-red-400' : 'text-amber-400')}>
                            {loan.dti_ratio != null ? `${(loan.dti_ratio * 100).toFixed(1)}%` : '—'}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 tabular-nums">
                          <span className={clsx(
                            loan.credit_score_at_origination
                              ? loan.credit_score_at_origination >= 720 ? 'text-green-400'
                              : loan.credit_score_at_origination >= 580 ? 'text-amber-400'
                              : 'text-red-400'
                              : 'text-t3'
                          )}>
                            {loan.credit_score_at_origination ?? '—'}
                          </span>
                        </td>
                        <td className="px-4 py-2.5">
                          <Badge
                            label={loan.status}
                            color={({
                              active: 'green', approved: 'green',
                              pending: 'amber',
                              rejected: 'red', completed: 'gray',
                            } as Record<string, 'green' | 'amber' | 'blue' | 'red' | 'gray'>)[loan.status] ?? 'gray'}
                          />
                        </td>
                        <td className="px-4 py-2.5">
                          {loan.is_delinquent
                            ? <span className="text-red-400 text-[10px]">⚠ {loan.days_past_due}d</span>
                            : <span className="text-green-400/60 text-[10px]">No</span>}
                        </td>
                      </tr>
                    ))
                  )}
                </motion.tbody>
              )}
            </AnimatePresence>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-white/[0.06] flex items-center justify-between">
            <span className="text-[10px] text-t3">
              Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total.toLocaleString()}
            </span>
            <div className="flex gap-1">
              <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                className="px-2 py-1 rounded text-xs text-t3 disabled:opacity-30 hover:bg-white/[0.05] transition-colors">
                ← Prev
              </button>
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                const start = Math.max(0, Math.min(page - 2, totalPages - 5));
                const p = start + i;
                return (
                  <button key={p} onClick={() => setPage(p)}
                    className={clsx('px-2 py-1 rounded text-xs transition-colors',
                      p === page ? 'bg-purple-500/20 text-purple-300' : 'text-t3 hover:bg-white/[0.05]')}>
                    {p + 1}
                  </button>
                );
              })}
              <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
                className="px-2 py-1 rounded text-xs text-t3 disabled:opacity-30 hover:bg-white/[0.05] transition-colors">
                Next →
              </button>
            </div>
          </div>
        )}
      </GlassCard>

      {/* Loan Detail Slide-in Panel */}
      <LoanDetailPanel
        loanId={selectedLoanId}
        onClose={() => setSelectedLoanId(null)}
      />
    </div>
  );
}
