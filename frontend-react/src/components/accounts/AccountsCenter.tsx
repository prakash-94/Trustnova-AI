/**
 * AccountsCenter — Bank-wide Accounts Operations Module
 *
 * ARCHITECTURE RULE: This component shows ALL accounts across the bank.
 * It is NOT filtered by a selected customer.  That separation is intentional:
 *
 *   Customer 360 → Customer Accounts tab  = one customer's accounts only
 *   AccountsCenter (this file)            = BANK-WIDE account management
 *
 * Use-case:
 *   A Branch Manager opens "Accounts" in the Bank Operations sidebar.
 *   She sees 1,000 total accounts, 940 active, 23 opened this month.
 *   She clicks "Savings" tab → filtered list of all savings accounts.
 *   She types "johnson" in search → finds all Johnson family accounts.
 *
 * Tabs (7):  Personal | Student | Business | Savings | Checking | Credit Cards | Dormant
 *
 * Data flow:
 *   1. On mount → accountsApi.stats()   → fills KPI cards + type chart
 *   2. On tab change → accountsApi.list({ account_type }) → fills table
 *   3. On search → accountsApi.list({ search }) → live filtered table
 *   4. Pagination via offset/limit query params
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';
import { accountsApi, type BankAccount, type AccountStats } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';
import Badge from '@/components/ui/Badge';
import type { CustomerSummary } from '@/types';

// ── Constants ────────────────────────────────────────────────────────────────

const PAGE_SIZE = 50;

/**
 * Tab definitions.
 * `type` is the value sent to the API as account_type param.
 * `all` means no filter (show everything).
 */
const TABS = [
  { id: 'all',         label: 'All Accounts',  icon: '🏛',  type: 'all' },
  { id: 'personal',    label: 'Personal',       icon: '👤',  type: 'personal' },
  { id: 'student',     label: 'Student',        icon: '🎓',  type: 'student' },
  { id: 'business',    label: 'Business',       icon: '🏢',  type: 'business' },
  { id: 'savings',     label: 'Savings',        icon: '💰',  type: 'savings' },
  { id: 'checking',    label: 'Checking',       icon: '✔',   type: 'checking' },
  { id: 'credit_card', label: 'Credit Cards',   icon: '💳',  type: 'credit_card' },
  { id: 'dormant',     label: 'Dormant',        icon: '💤',  type: 'dormant' },
] as const;

type TabId = (typeof TABS)[number]['id'];

// ── Formatters ───────────────────────────────────────────────────────────────

const fmt$ = (cents: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(cents / 100);

const fmtK = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));

// ── Mini Inline Bar Chart ────────────────────────────────────────────────────
/**
 * MiniBarChart renders an animated SVG/CSS bar chart for the account type
 * distribution.  No external chart library — uses framer-motion for bars.
 *
 * Input:  data[] = [{ label, value, color }]
 * Output: A horizontal row of bars with relative heights.
 */
const BAR_MAX_H = 140;

function MiniBarChart({ data }: { data: { label: string; value: number; color: string }[] }) {
  const max = Math.max(...data.map(d => d.value), 1);
  return (
    <div className="flex items-end gap-2" style={{ height: `${BAR_MAX_H + 36}px` }}>
      {data.map((d, i) => {
        const barH = Math.max(4, Math.round((d.value / max) * BAR_MAX_H));
        return (
          <div key={d.label} className="flex flex-col items-center gap-1 flex-1 min-w-0">
            <span className="text-[9px] text-t2 tabular-nums font-medium leading-none">{fmtK(d.value)}</span>
            <motion.div
              initial={{ height: 0 }}
              animate={{ height: `${barH}px` }}
              transition={{ delay: i * 0.06, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
              className={clsx('w-full rounded-t', d.color)}
              title={`${d.label}: ${d.value}`}
            />
            <span className="text-[9px] text-t3 capitalize leading-none truncate w-full text-center">{d.label}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── KPI Card ─────────────────────────────────────────────────────────────────
/**
 * KpiCard shows a single metric with label, value, and optional sub-text.
 * Used in the row of 5 bank-wide account statistics at the top.
 *
 * Input:  { label, value, sub, color, icon }
 * Output: Rendered glass card with colored top border.
 */
function KpiCard({ label, value, sub, color, icon }: {
  label: string; value: string; sub?: string; color: string; icon: string;
}) {
  return (
    <GlassCard animate={false} className={clsx('p-4 border-t-2', color)}>
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[10px] text-t3 uppercase tracking-wider mb-1">{label}</div>
          <div className="text-2xl font-bold text-t1">{value}</div>
          {sub && <div className="text-[10px] text-t3 mt-0.5">{sub}</div>}
        </div>
        <span className="text-xl opacity-60">{icon}</span>
      </div>
    </GlassCard>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

interface AccountsCenterProps {
  onSelectCustomer?: (c: CustomerSummary) => void;
}

export default function AccountsCenter({ onSelectCustomer }: AccountsCenterProps) {
  // Active tab selection drives the API filter
  const [activeTab, setActiveTab] = useState<TabId>('all');

  // KPI stats loaded once on mount (bank-wide totals + by-type breakdown)
  const [stats, setStats] = useState<AccountStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  // Paginated account rows for the active tab
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);          // current page (0-indexed)
  const [tableLoading, setTableLoading] = useState(false);

  // Search: debounced so we don't fire on every keystroke
  const [search, setSearch] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // ── Data fetching ──────────────────────────────────────────────────────────

  /** Load the bank-wide KPI stats once on mount. */
  useEffect(() => {
    accountsApi.stats()
      .then(s => setStats(s))
      .catch(() => {})
      .finally(() => setStatsLoading(false));
  }, []);

  /**
   * Load accounts table whenever tab, page, or search changes.
   *
   * The API call encodes business logic:
   *   - activeTab = 'all'     → no account_type filter
   *   - activeTab = 'dormant' → special backend rule (age > 730 days + low balance)
   *   - otherwise             → pass account_type param directly
   */
  const loadAccounts = useCallback(async () => {
    setTableLoading(true);
    try {
      const tabDef = TABS.find(t => t.id === activeTab)!;
      const res = await accountsApi.list({
        account_type: tabDef.type === 'all' ? undefined : tabDef.type,
        search: debouncedSearch || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setAccounts(res.accounts);
      setTotal(res.total);
    } catch {
      setAccounts([]);
      setTotal(0);
    } finally {
      setTableLoading(false);
    }
  }, [activeTab, page, debouncedSearch]);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);

  // Debounce search input (300 ms) to avoid flooding the backend
  const handleSearchChange = (val: string) => {
    setSearch(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(val);
      setPage(0);   // reset to first page on new search
    }, 300);
  };

  const handleTabChange = (id: TabId) => {
    setActiveTab(id);
    setPage(0);     // reset pagination on tab switch
    setSearch('');
    setDebouncedSearch('');
  };

  // ── Derived values ─────────────────────────────────────────────────────────

  const totalPages = Math.ceil(total / PAGE_SIZE);

  // Build bar chart data from the stats.by_type breakdown
  const chartData = stats
    ? Object.entries(stats.by_type).map(([type, info], i) => ({
        label: type,
        value: info.count,
        color: [
          'bg-purple-400/70', 'bg-blue-400/70', 'bg-green-400/70',
          'bg-amber-400/70',  'bg-cyan-400/70',  'bg-red-400/70',
          'bg-indigo-400/70',
        ][i % 7],
      }))
    : [];

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">

      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <GlassCard animate={false} className="px-5 py-4">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-t1">Accounts Operations</h2>
            <p className="text-xs text-t3 mt-0.5">
              Bank-wide account management — all {stats ? stats.total_accounts.toLocaleString() : '…'} accounts
              across all branches and customer segments
            </p>
          </div>
          <span className="text-2xl">🏛</span>
        </div>
      </GlassCard>

      {/* ── KPI Cards (5 metrics) ────────────────────────────────────────────── */}
      {/*
        These cards show BANK-WIDE totals, not customer-specific numbers.
        Each card is populated from GET /accounts/stats.
      */}
      <div className="grid grid-cols-5 gap-3">
        <KpiCard
          label="Total Accounts"
          value={statsLoading ? '…' : (stats?.total_accounts ?? 0).toLocaleString()}
          sub="across all branches"
          color="border-purple-500/40"
          icon="🏛"
        />
        <KpiCard
          label="Active Accounts"
          value={statsLoading ? '…' : (stats?.active_accounts ?? 0).toLocaleString()}
          sub={stats ? `${Math.round((stats.active_accounts / stats.total_accounts) * 100)}% of total` : ''}
          color="border-green-500/40"
          icon="✅"
        />
        <KpiCard
          label="Dormant Accounts"
          value={statsLoading ? '…' : (stats?.dormant_accounts ?? 0).toLocaleString()}
          sub="inactive > 2 years"
          color="border-amber-500/40"
          icon="💤"
        />
        <KpiCard
          label="New This Month"
          value={statsLoading ? '…' : (stats?.new_this_month ?? 0).toLocaleString()}
          sub="opened ≤ 31 days ago"
          color="border-blue-500/40"
          icon="🆕"
        />
        <KpiCard
          label="Total Deposits"
          value={statsLoading ? '…' : fmt$(stats?.total_balance_cents ?? 0)}
          sub={stats ? `avg ${fmt$(stats.avg_balance_cents)}` : ''}
          color="border-cyan-500/40"
          icon="💵"
        />
      </div>

      {/* ── Account type distribution chart ──────────────────────────────────── */}
      {/*
        This is NOT a chart library — it's a CSS/Framer-Motion bar chart
        built inline.  Each bar represents one account type bucket.
        The bar height is proportional to the count within that bucket.
      */}
      {chartData.length > 0 && (
        <GlassCard animate={false} className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-t1">Account Type Distribution</h3>
            <span className="text-xs text-t3 font-mono">{stats?.total_accounts.toLocaleString()} total accounts</span>
          </div>
          <div className="flex gap-8 items-end">
            {/* Bar chart — takes most of the width */}
            <div className="flex-1 min-w-0">
              <MiniBarChart data={chartData} />
            </div>
            {/* Legend on the right */}
            <div className="flex-shrink-0 grid grid-cols-2 gap-x-6 gap-y-2 pb-2">
              {chartData.map(d => (
                <div key={d.label} className="flex items-center gap-2 text-xs">
                  <div className={clsx('w-2.5 h-2.5 rounded flex-shrink-0', d.color)} />
                  <span className="text-t3 capitalize">{d.label}</span>
                  <span className="ml-auto text-t1 font-semibold tabular-nums">{d.value.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        </GlassCard>
      )}

      {/* ── Tab bar ──────────────────────────────────────────────────────────── */}
      {/*
        Switching tabs fires accountsApi.list({ account_type: tab.type }).
        The "dormant" tab uses a backend composite rule (age > 730 AND balance < 100).
        All other tabs use a simple account_type = ? filter.
      */}
      <GlassCard animate={false} className="px-4 py-2.5">
        <div className="flex gap-1 flex-wrap">
          {TABS.map(tab => {
            const count = tab.id === 'all'
              ? stats?.total_accounts
              : tab.id === 'dormant'
              ? stats?.dormant_accounts
              : stats?.by_type[tab.type]?.count;

            return (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap',
                  activeTab === tab.id
                    ? 'bg-purple-500/15 border border-purple-500/25 text-purple-300'
                    : 'text-t3 hover:text-t2 hover:bg-white/[0.04]',
                )}
              >
                <span>{tab.icon}</span>
                <span>{tab.label}</span>
                {count != null && (
                  <span className={clsx(
                    'text-[9px] px-1 rounded',
                    activeTab === tab.id ? 'text-purple-400' : 'text-t3',
                  )}>
                    {count.toLocaleString()}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </GlassCard>

      {/* ── Search + filter bar ───────────────────────────────────────────────── */}
      <GlassCard animate={false} className="px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <input
              type="text"
              value={search}
              onChange={e => handleSearchChange(e.target.value)}
              placeholder="Search by customer name or email…"
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-2 pl-9 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 transition-colors"
            />
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-t3 text-xs">🔍</span>
          </div>
          {tableLoading && (
            <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
          )}
          <div className="text-[10px] text-t3 whitespace-nowrap">
            {total.toLocaleString()} result{total !== 1 ? 's' : ''}
          </div>
        </div>
      </GlassCard>

      {/* ── Accounts Table ───────────────────────────────────────────────────── */}
      {/*
        Each row represents one bank account (= one customer's primary account).
        Columns: Customer, Account No., Type, Status, Balance, Credit Score, Age.

        Input:  accounts[] from accountsApi.list()
        Output: Rendered table with colored status badges and formatted money.
      */}
      <GlassCard animate={false} className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/[0.06]">
                {['Customer', 'Account No.', 'Type', 'Status', 'Balance', 'Credit Score', 'Account Age', 'Risk'].map(h => (
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
                    <td colSpan={8} className="py-16 text-center text-xs text-t3">
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                        Loading accounts…
                      </div>
                    </td>
                  </tr>
                </tbody>
              ) : (
                <motion.tbody
                  key={`${activeTab}-${page}-${debouncedSearch}`}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  className="divide-y divide-white/[0.04]"
                >
                  {accounts.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-16 text-center text-sm text-t3">
                        <div className="text-2xl mb-2">🏦</div>
                        No accounts found
                        {debouncedSearch && ` for "${debouncedSearch}"`}
                      </td>
                    </tr>
                  ) : (
                    accounts.map(acc => (
                      <tr
                        key={acc.id}
                        onClick={() => onSelectCustomer?.({ customer_id: acc.customer_id, name: acc.customer_name })}
                        className={clsx(
                          'transition-colors',
                          onSelectCustomer
                            ? 'cursor-pointer hover:bg-purple-500/[0.08] hover:border-purple-500/20 group'
                            : 'hover:bg-white/[0.02]',
                        )}
                      >
                        {/* Customer name */}
                        <td className="px-4 py-3">
                          <div className={clsx(
                            'font-medium truncate max-w-[140px]',
                            onSelectCustomer ? 'text-t1 group-hover:text-purple-300 transition-colors' : 'text-t1',
                          )}>{acc.customer_name}</div>
                          <div className="text-[9px] text-t3 font-mono">{acc.customer_id.slice(0, 8)}</div>
                          {onSelectCustomer && (
                            <div className="text-[9px] text-purple-400/50 group-hover:text-purple-400/80 transition-colors">Click to open profile →</div>
                          )}
                        </td>
                        {/* Masked account number */}
                        <td className="px-4 py-3 font-mono text-t3">{acc.account_number}</td>
                        {/* Account type badge */}
                        <td className="px-4 py-3">
                          <span className="px-1.5 py-0.5 rounded bg-purple-500/10 border border-purple-500/20 text-purple-300 text-[9px] capitalize">
                            {acc.account_type}
                          </span>
                        </td>
                        {/* Status badge */}
                        <td className="px-4 py-3">
                          <Badge
                            label={acc.status}
                            color={acc.status === 'active' ? 'green' : 'amber'}
                          />
                        </td>
                        {/* Balance */}
                        <td className="px-4 py-3 font-semibold text-green-400 tabular-nums whitespace-nowrap">
                          {fmt$(acc.balance_cents)}
                        </td>
                        {/* Credit score with color coding */}
                        <td className="px-4 py-3 tabular-nums">
                          {acc.credit_score != null ? (
                            <span className={clsx(
                              'font-medium',
                              acc.credit_score >= 720 ? 'text-green-400'
                              : acc.credit_score >= 580 ? 'text-amber-400'
                              : 'text-red-400',
                            )}>
                              {acc.credit_score}
                            </span>
                          ) : (
                            <span className="text-t3">—</span>
                          )}
                        </td>
                        {/* Account age in days */}
                        <td className="px-4 py-3 text-t3 tabular-nums whitespace-nowrap">
                          {acc.account_age_days == null
                            ? <span className="text-t3">—</span>
                            : acc.account_age_days > 365
                            ? `${(acc.account_age_days / 365).toFixed(1)} yr`
                            : `${acc.account_age_days} d`}
                        </td>
                        {/* Risk level */}
                        <td className="px-4 py-3">
                          <Badge
                            label={acc.risk_level.replace('_', ' ')}
                            color={
                              acc.risk_level === 'low' ? 'green'
                              : acc.risk_level === 'medium' ? 'amber'
                              : 'red'
                            }
                          />
                        </td>
                      </tr>
                    ))
                  )}
                </motion.tbody>
              )}
            </AnimatePresence>
          </table>
        </div>

        {/* ── Pagination controls ───────────────────────────────────────────── */}
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-white/[0.06] flex items-center justify-between">
            <span className="text-[10px] text-t3">
              Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total.toLocaleString()}
            </span>
            <div className="flex gap-1">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-2 py-1 rounded text-xs text-t3 disabled:opacity-30 hover:bg-white/[0.05] transition-colors"
              >
                ← Prev
              </button>
              {/* Show up to 5 page numbers centred around current page */}
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                const start = Math.max(0, Math.min(page - 2, totalPages - 5));
                const p = start + i;
                return (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    className={clsx(
                      'px-2 py-1 rounded text-xs transition-colors',
                      p === page
                        ? 'bg-purple-500/20 text-purple-300'
                        : 'text-t3 hover:bg-white/[0.05]',
                    )}
                  >
                    {p + 1}
                  </button>
                );
              })}
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-2 py-1 rounded text-xs text-t3 disabled:opacity-30 hover:bg-white/[0.05] transition-colors"
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
