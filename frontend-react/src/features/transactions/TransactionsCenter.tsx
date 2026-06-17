/**
 * TransactionsCenter — Bank-wide Transaction Operations Module
 *
 * ARCHITECTURE RULE: This component shows ALL transactions across the bank,
 * grouped by time period.  It is NOT filtered by a selected customer.
 *
 *   Customer 360 → Transactions tab  = one customer's transactions only
 *   TransactionsCenter (this file)   = BANK-WIDE transaction analytics
 *
 * Use-case:
 *   An Operations Analyst opens "Transactions" in the Bank Operations sidebar.
 *   She selects the "Monthly" tab and sees:
 *     - 1,450 total transactions in the last 30 days
 *     - $185,000 total volume
 *     - 45 fraud alerts (3.1% rate)
 *     - A bar chart showing daily transaction counts
 *     - A breakdown by merchant category (food, retail, travel, etc.)
 *     - A paginated table of all transactions
 *
 * Time Period Tabs (6):
 *   Daily → last 24h | Weekly → 7 days | Monthly → 30 days
 *   Quarterly → 90 days | Half-Yearly → 180 days | Annual → 365 days
 *
 * Data flow:
 *   1. On tab select → bankTransactionsApi.stats(period) → KPIs + trend + categories
 *   2. On table load → bankTransactionsApi.list({ period }) → paginated rows
 *   3. Fraud toggle → bankTransactionsApi.list({ is_fraud: true }) → fraud-only view
 */

import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';
import { bankTransactionsApi, type TransactionStats, type BankTransaction } from '@/services/api';
import GlassCard from '@/components/common/GlassCard';
import Badge from '@/components/common/Badge';

// ── Constants ────────────────────────────────────────────────────────────────

const PAGE_SIZE = 50;

/**
 * Period tabs — each one maps to a time window the backend uses.
 * The `period` string is passed as a query param: ?period=monthly
 */
const PERIODS = [
  { id: 'daily',       label: 'Daily',       icon: '📅', days: 1 },
  { id: 'weekly',      label: 'Weekly',      icon: '📆', days: 7 },
  { id: 'monthly',     label: 'Monthly',     icon: '🗓', days: 30 },
  { id: 'quarterly',   label: 'Quarterly',   icon: '📊', days: 90 },
  { id: 'half_yearly', label: 'Half-Yearly', icon: '📈', days: 180 },
  { id: 'annual',      label: 'Annual',      icon: '📋', days: 365 },
] as const;

type PeriodId = (typeof PERIODS)[number]['id'];

// ── Formatters ───────────────────────────────────────────────────────────────

const fmt$ = (cents: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(cents / 100);

const fmtPct = (n: number, d: number) => (d > 0 ? `${((n / d) * 100).toFixed(1)}%` : '0%');

// ── Trend Bar Chart ───────────────────────────────────────────────────────────
/**
 * TrendChart renders an animated bar chart of daily transaction counts.
 *
 * Input:  trend[] = [{ day: "2024-04-01", count: 48, volume_cents: 610000 }]
 * Output: Responsive row of gradient bars with a tooltip on hover.
 *
 * Design:
 *   - Bars show relative height (normalised to max count in the dataset)
 *   - X-axis shows abbreviated date labels
 *   - Hover tooltip shows exact count and volume
 *   - Animated entry (height grows from 0) via framer-motion
 */
function TrendChart({ trend, period }: { trend: TransactionStats['trend']; period: string }) {
  const max = Math.max(...trend.map(d => d.count), 1);

  if (trend.length === 0) {
    return (
      <div className="flex items-center justify-center h-24 text-xs text-t3">
        No trend data available for this period
      </div>
    );
  }

  // Format bar label based on period type:
  //   daily        → "2026-05-12 14"  → "2 PM"
  //   weekly/monthly → "2026-05-06"   → "May 6"
  //   quarterly/half_yearly → "2026-07" (year-week) → "W7"
  //   annual       → "2025-05"        → "May"
  function formatLabel(day: string): string {
    if (/^\d{4}-\d{2}-\d{2} \d{2}$/.test(day)) {
      const h = parseInt(day.slice(-2), 10);
      return `${h === 0 ? '12' : h > 12 ? h - 12 : h}${h >= 12 ? 'p' : 'a'}`;
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(day)) {
      const dt = new Date(day + 'T00:00:00');
      return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
    if (/^\d{4}-\d{2}$/.test(day)) {
      const [, num] = day.split('-').map(Number);
      if (period === 'quarterly' || period === 'half_yearly') return `W${num}`;
      const dt = new Date(parseInt(day), num - 1, 1);
      return dt.toLocaleDateString('en-US', { month: 'short' });
    }
    return day;
  }

  return (
    <div className="flex items-end gap-px h-24 overflow-hidden">
      {trend.map((d, i) => {
        const heightPct = (d.count / max) * 100;
        const label = formatLabel(d.day);

        return (
          <motion.div
            key={d.day}
            className="group relative flex flex-col items-center flex-1 min-w-0"
            style={{ height: '100%', alignItems: 'center', justifyContent: 'flex-end', display: 'flex' }}
          >
            {/* Bar */}
            <motion.div
              initial={{ height: 0 }}
              animate={{ height: `${heightPct}%` }}
              transition={{ delay: i * 0.015, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              className="w-full rounded-t-sm bg-gradient-to-t from-purple-600/60 to-purple-400/80 hover:from-purple-500/80 hover:to-purple-300 transition-colors cursor-default"
            />
            {/* Tooltip on hover */}
            <div className="absolute bottom-full mb-1 z-10 hidden group-hover:flex flex-col items-center pointer-events-none">
              <div className="bg-gray-900 border border-white/10 rounded-lg px-2 py-1.5 text-[9px] whitespace-nowrap shadow-xl">
                <div className="text-t1 font-medium">{label}</div>
                <div className="text-purple-300">{d.count} transactions</div>
                <div className="text-t3">{fmt$(d.volume_cents)}</div>
              </div>
              <div className="w-1.5 h-1.5 bg-gray-900 rotate-45 border-r border-b border-white/10 -mt-1" />
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

// ── Category Breakdown ────────────────────────────────────────────────────────
/**
 * CategoryBreakdown renders horizontal bars for merchant category distribution.
 *
 * Input:  by_category = { "food": { count: 312, volume_cents: 4620000 }, ... }
 * Output: Sorted horizontal progress bars with count + volume labels.
 */
function CategoryBreakdown({ data }: { data: TransactionStats['by_category'] }) {
  const entries = Object.entries(data).sort((a, b) => b[1].count - a[1].count);
  const maxCount = entries[0]?.[1].count ?? 1;

  const CATEGORY_COLORS: Record<string, string> = {
    food:       'bg-orange-400/70',
    retail:     'bg-blue-400/70',
    travel:     'bg-cyan-400/70',
    healthcare: 'bg-green-400/70',
    utilities:  'bg-yellow-400/70',
    finance:    'bg-purple-400/70',
    other:      'bg-gray-400/70',
  };

  return (
    <div className="space-y-2">
      {entries.map(([cat, info]) => (
        <div key={cat}>
          <div className="flex justify-between text-[10px] mb-0.5">
            <span className="text-t2 capitalize">{cat}</span>
            <span className="text-t3 tabular-nums">{info.count} txns · {fmt$(info.volume_cents)}</span>
          </div>
          <div className="w-full h-1.5 rounded-full bg-white/[0.06]">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${(info.count / maxCount) * 100}%` }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              className={clsx('h-full rounded-full', CATEGORY_COLORS[cat] ?? 'bg-gray-400/70')}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Fraud Alert Helpers ──────────────────────────────────────────────────────

const FRAUD_INFO: Record<string, { title: string; explanation: string; triggers: string[] }> = {
  card_fraud: {
    title: 'Unauthorized Card Transaction',
    explanation: 'An unauthorized card transaction was detected. The card was used at an unusual merchant, location, or time inconsistent with the account holder\'s spending history. Per Section 3.5 of the Risk Management Policy, customers have zero liability for reported unauthorized transactions.',
    triggers: [
      'Card used at unfamiliar or high-risk merchant',
      'Transaction in unusual geographic location',
      'Multiple rapid transactions in short timeframe',
      'Transaction outside normal spending hours',
    ],
  },
  identity_theft: {
    title: 'Identity Theft Detected',
    explanation: 'Suspicious identity patterns indicate this account may have been accessed by an unauthorized individual using stolen personal information or credentials. Per Section 3.2 of the Risk Management Policy (Category A: Identity Theft), this requires immediate account review.',
    triggers: [
      'Login from unrecognized device or IP address',
      'Multiple failed authentication attempts preceding access',
      'Account information changed after unusual login',
      'Identity document mismatch at verification step',
    ],
  },
  account_takeover: {
    title: 'Account Takeover Attempt',
    explanation: 'Behavioral analytics detected patterns consistent with an account takeover: unusual login times, unrecognized devices, rapid profile changes, or high-value transactions immediately after a new login. Immediate account freeze may be required per Section 3.3 of the Fraud Investigation Procedure.',
    triggers: [
      'Login from new device or unrecognized location',
      'Password or contact info reset just before large transaction',
      'Session activity pattern inconsistent with account owner',
      'Multiple accounts showing same anomaly pattern',
    ],
  },
  transaction_fraud: {
    title: 'Suspicious Transaction Pattern',
    explanation: 'This transaction exhibits behavioral anomalies compared to the customer\'s historical profile. The ML fraud detection model (Section 3.1, Risk Management Policy) flagged amount, timing, merchant type, or location as inconsistent with established spending behavior.',
    triggers: [
      'Transaction amount significantly above the customer\'s normal average',
      'Merchant category not in customer\'s typical spending history',
      'Transaction velocity exceeds historical baseline',
      'Unusual transaction channel or time of day',
    ],
  },
  unusual_activity: {
    title: 'Unusual Account Activity',
    explanation: 'Transaction monitoring rules (Section 4.1, Risk Management Policy) detected activity that deviates significantly from this customer\'s established behavioral baseline, including dormant accounts re-activated or mismatched transaction patterns vs. customer profile.',
    triggers: [
      'Account activity pattern changed significantly from historical norm',
      'Dormant account suddenly activated with large transaction',
      'Geographic spread inconsistent with normal travel patterns',
      'Multiple large transactions in a short period',
    ],
  },
  aml_alert: {
    title: 'Anti-Money Laundering Alert',
    explanation: 'AML transaction monitoring rules were triggered. Per Section 3.2 of the Compliance AML/KYC Policy, the detected pattern may indicate structuring, layering, or integration — key money laundering indicators. A BSA Officer review and potential SAR filing (31 C.F.R. § 1020.320) may be required.',
    triggers: [
      'Multiple transactions near the $10,000 CTR reporting threshold',
      'Rapid in-and-out fund movement (layering pattern)',
      'Wire transfers to FATF high-risk jurisdictions',
      'Mismatched transaction patterns vs. customer risk profile',
    ],
  },
  structuring: {
    title: 'Potential Structuring (CTR Avoidance)',
    explanation: 'Multiple transactions have been structured to remain just below the $10,000 Currency Transaction Report (CTR) threshold. Structuring is a federal crime under 31 U.S.C. § 5324. Per Section 5.4 of the Compliance AML/KYC Policy, a SAR must be filed with FinCEN within 30 days.',
    triggers: [
      'Multiple cash deposits/withdrawals in the $9,000–$9,999 range',
      'Aggregated daily transactions approaching the $10,000 CTR limit',
      'Pattern of transactions split across multiple days or branches',
      'Customer previously inquired about CTR reporting requirements',
    ],
  },
  wire_fraud: {
    title: 'Suspicious Wire Transfer',
    explanation: 'An unauthorized or suspicious wire transfer was detected. Per Section 3.4 of the Operations Procedures, wires above $10,000 require banker review and OFAC screening. The destination, amount, or timing is inconsistent with the customer\'s known transaction history.',
    triggers: [
      'Wire to a sanctioned or FATF high-risk jurisdiction',
      'First-time wire to a new or unverified beneficiary',
      'Wire amount significantly inconsistent with customer profile',
      'Wire initiated immediately after account takeover indicators',
    ],
  },
  check_fraud: {
    title: 'Check Fraud Detected',
    explanation: 'A counterfeit, forged, or altered check was identified (Section 3.2, Category C: Check Fraud). The check details do not match account holder records or exhibit characteristics consistent with check kiting or physical alteration of the document.',
    triggers: [
      'Check MICR encoding does not match account records',
      'Large check deposit followed immediately by withdrawal (kiting pattern)',
      'Multiple checks returned NSF in rapid succession',
      'Payee name or amount shows signs of alteration',
    ],
  },
};

function getFraudInfo(fraudType: string) {
  return FRAUD_INFO[fraudType] ?? {
    title: fraudType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    explanation: `A ${fraudType.replace(/_/g, ' ')} alert was generated by TrustNova's automated fraud detection system (Section 3.1, Risk Management Policy) based on ML model scoring and rule-based transaction monitoring. The transaction\'s risk score exceeds the review threshold.`,
    triggers: [
      'Automated ML fraud model score exceeded review threshold',
      'Transaction pattern deviates from customer behavioral baseline',
      'Rule-based monitoring system flagged transaction characteristics',
    ],
  };
}

const severityColor = (s: string): 'red' | 'amber' | 'blue' | 'green' =>
  ({ critical: 'red', high: 'amber', medium: 'blue', low: 'green' } as Record<string, 'red' | 'amber' | 'blue' | 'green'>)[s] ?? 'green';

const statusColor = (s: string): 'amber' | 'blue' | 'green' | 'gray' =>
  ({ open: 'amber', investigating: 'blue', reviewing: 'amber', resolved: 'green', false_positive: 'green' } as Record<string, 'amber' | 'blue' | 'green' | 'gray'>)[s] ?? 'gray';

const riskLabel = (score: number) => score >= 0.8 ? 'Critical' : score >= 0.6 ? 'High' : score >= 0.4 ? 'Medium' : 'Low';
const riskColor = (score: number) => score >= 0.8 ? 'text-red-400' : score >= 0.6 ? 'text-amber-400' : 'text-blue-400';
const riskBarColor = (score: number) => score >= 0.8 ? 'bg-red-400' : score >= 0.6 ? 'bg-amber-400' : 'bg-blue-400';

// ── KPI Card ─────────────────────────────────────────────────────────────────
function KpiCard({
  label, value, sub, accentClass, icon, onClick,
}: {
  label: string; value: string; sub?: string; accentClass: string; icon: string;
  onClick?: () => void;
}) {
  return (
    <GlassCard animate={false}
      className={clsx('p-4 border-t-2', accentClass, onClick && 'cursor-pointer hover:brightness-125 transition-all')}
      onClick={onClick}
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[10px] text-t3 uppercase tracking-wider mb-1">{label}</div>
          <div className="text-xl font-bold text-t1 tabular-nums">{value}</div>
          {sub && <div className="text-[10px] text-t3 mt-0.5">{sub}</div>}
        </div>
        <span className="text-xl opacity-60">{icon}</span>
      </div>
      {onClick && (
        <div className="mt-2 text-[9px] text-red-400/70 font-medium">Click to view details →</div>
      )}
    </GlassCard>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function TransactionsCenter() {
  const [activePeriod, setActivePeriod] = useState<PeriodId>('monthly');
  const [stats, setStats] = useState<TransactionStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  // Table state
  const [txns, setTxns] = useState<BankTransaction[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [tableLoading, setTableLoading] = useState(false);

  // Filters
  const [fraudOnly, setFraudOnly] = useState(false);
  const [search, setSearch] = useState('');

  // Fraud Alerts Modal
  const [showFraudModal, setShowFraudModal] = useState(false);
  const [fraudTxns, setFraudTxns] = useState<BankTransaction[]>([]);
  const [fraudLoading, setFraudLoading] = useState(false);
  const [selectedTxn, setSelectedTxn] = useState<BankTransaction | null>(null);
  const [fraudFilter, setFraudFilter] = useState<string>('all');

  // Infer fraud severity from merchant_risk field (can be numeric 0-100 or string low/medium/high)
  function riskToScore(r: string | number): number {
    if (typeof r === 'number') return r / 100;
    return r === 'high' ? 0.85 : r === 'medium' ? 0.55 : 0.25;
  }

  function riskToSeverity(r: string | number): string {
    const s = riskToScore(r);
    return s >= 0.8 ? 'critical' : s >= 0.6 ? 'high' : s >= 0.4 ? 'medium' : 'low';
  }

  function inferFraudType(tx: BankTransaction): string {
    const cat = (tx.merchant_category ?? '').toLowerCase();
    const name = (tx.merchant_name ?? '').toLowerCase();
    if (cat === 'crypto' || name.includes('coinbase') || name.includes('binance')) return 'aml_alert';
    if (cat === 'transfer' || tx.channel === 'wire') return 'wire_fraud';
    if (riskToScore(tx.merchant_risk) >= 0.8) return 'card_fraud';
    if (riskToScore(tx.merchant_risk) >= 0.6) return 'transaction_fraud';
    return 'unusual_activity';
  }

  // Derived: filtered fraud transactions
  const filteredFraudTxns = fraudFilter === 'all' ? fraudTxns
    : fraudTxns.filter(tx => riskToSeverity(tx.merchant_risk) === fraudFilter);

  // ── Data fetching ──────────────────────────────────────────────────────────

  /** Load period stats whenever the active tab changes. */
  useEffect(() => {
    setStatsLoading(true);
    bankTransactionsApi.stats(activePeriod)
      .then(s => setStats(s))
      .catch(() => {})
      .finally(() => setStatsLoading(false));
  }, [activePeriod]);

  /** Load transaction table whenever period / page / filters change. */
  const loadTransactions = useCallback(async () => {
    setTableLoading(true);
    try {
      const res = await bankTransactionsApi.list({
        period: activePeriod,
        is_fraud: fraudOnly ? true : undefined,
        search: search || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setTxns(res.transactions);
      setTotal(res.total);
    } catch {
      setTxns([]);
      setTotal(0);
    } finally {
      setTableLoading(false);
    }
  }, [activePeriod, page, fraudOnly, search]);

  useEffect(() => { loadTransactions(); }, [loadTransactions]);

  /** Load fraud transactions when modal is opened. */
  useEffect(() => {
    if (!showFraudModal) return;
    setFraudLoading(true);
    setSelectedTxn(null);
    setFraudFilter('all');
    bankTransactionsApi.list({ is_fraud: true, period: activePeriod, limit: 500 })
      .then(res => setFraudTxns(res.transactions ?? []))
      .catch((err) => { console.error('[FraudModal] fetch failed:', err); setFraudTxns([]); })
      .finally(() => setFraudLoading(false));
  }, [showFraudModal, activePeriod]);

  const handlePeriodChange = (id: PeriodId) => {
    setActivePeriod(id);
    setPage(0);
    setFraudOnly(false);
    setSearch('');
  };

  // ── Derived ───────────────────────────────────────────────────────────────

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const fraudRate = stats
    ? fmtPct(stats.fraud_count, stats.total_transactions)
    : '0%';

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">

      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <GlassCard animate={false} className="px-5 py-4">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-t1">Transaction Operations Center</h2>
            <p className="text-xs text-t3 mt-0.5">
              Bank-wide transaction analytics — all {stats ? stats.all_time_total.toLocaleString() : '…'} transactions
              across the institution, grouped by time period
            </p>
          </div>
          <span className="text-2xl">↔</span>
        </div>
      </GlassCard>

      {/* ── Period tabs ───────────────────────────────────────────────────── */}
      <GlassCard animate={false} className="px-4 py-2.5">
        <div className="flex gap-1">
          {PERIODS.map(p => (
            <button
              key={p.id}
              onClick={() => handlePeriodChange(p.id)}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap',
                activePeriod === p.id
                  ? 'bg-purple-500/15 border border-purple-500/25 text-purple-300'
                  : 'text-t3 hover:text-t2 hover:bg-white/[0.04]',
              )}
            >
              <span>{p.icon}</span>
              <span>{p.label}</span>
              <span className="text-[9px] text-t3">({p.days}d)</span>
            </button>
          ))}
        </div>
      </GlassCard>

      {/* ── 6 KPI Cards ─────────────────────────────────────────────────────── */}
      {/*
        Each card shows a metric for the SELECTED PERIOD only.
        e.g., if Monthly tab is active → "last 30 days" totals.
        These are populated from GET /transactions/stats?period=monthly.
      */}
      <div className="grid grid-cols-6 gap-3">
        <KpiCard
          label="Total Transactions"
          value={statsLoading ? '…' : (stats?.total_transactions ?? 0).toLocaleString()}
          sub={`of ${stats?.all_time_total.toLocaleString() ?? '…'} all-time`}
          accentClass="border-purple-500/40"
          icon="↔"
        />
        <KpiCard
          label="Total Volume"
          value={statsLoading ? '…' : fmt$(stats?.total_volume_cents ?? 0)}
          accentClass="border-blue-500/40"
          icon="💵"
        />
        <KpiCard
          label="Avg Transaction"
          value={statsLoading ? '…' : fmt$(stats?.avg_amount_cents ?? 0)}
          accentClass="border-cyan-500/40"
          icon="📊"
        />
        <KpiCard
          label="Fraud Alerts"
          value={statsLoading ? '…' : (stats?.fraud_count ?? 0).toLocaleString()}
          sub={`${fraudRate} fraud rate`}
          accentClass="border-red-500/40"
          icon="🚨"
          onClick={() => setShowFraudModal(true)}
        />
        <KpiCard
          label="Failed Txns"
          value={statsLoading ? '…' : (stats?.failed_count ?? 0).toLocaleString()}
          sub="processing errors"
          accentClass="border-amber-500/40"
          icon="❌"
        />
        <KpiCard
          label="Flagged Txns"
          value={statsLoading ? '…' : (stats?.fraud_count ?? 0).toLocaleString()}
          sub="require review"
          accentClass="border-orange-500/40"
          icon="⚠"
        />
      </div>

      {/* ── Analytics: Trend Chart + Category Breakdown ─────────────────────── */}
      <div className="grid grid-cols-5 gap-4">

        {/* Trend bar chart (3/5 width) */}
        <GlassCard animate={false} className="col-span-3 p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold text-t1">Transaction Volume Trend</h3>
            <span className="text-[10px] text-t3">
              {PERIODS.find(p => p.id === activePeriod)?.label} — last {PERIODS.find(p => p.id === activePeriod)?.days}d
            </span>
          </div>
          {statsLoading ? (
            <div className="flex items-center justify-center h-24 text-xs text-t3">
              <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mr-2" />
              Loading chart data…
            </div>
          ) : (
            <AnimatePresence mode="wait">
              <motion.div
                key={activePeriod}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <TrendChart trend={stats?.trend ?? []} period={activePeriod} />
              </motion.div>
            </AnimatePresence>
          )}
          <div className="flex justify-between text-[9px] text-t3 mt-1 px-0.5">
            <span>{stats?.trend[0]?.day ?? ''}</span>
            <span>← transaction volume →</span>
            <span>{stats?.trend[stats.trend.length - 1]?.day ?? ''}</span>
          </div>
        </GlassCard>

        {/* Category breakdown (2/5 width) */}
        <GlassCard animate={false} className="col-span-2 p-4">
          <h3 className="text-xs font-semibold text-t1 mb-3">Category Breakdown</h3>
          {statsLoading ? (
            <div className="flex items-center justify-center h-24 text-xs text-t3">
              Loading…
            </div>
          ) : (
            <AnimatePresence mode="wait">
              <motion.div key={activePeriod} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <CategoryBreakdown data={stats?.by_category ?? {}} />
              </motion.div>
            </AnimatePresence>
          )}
        </GlassCard>
      </div>

      {/* ── Table filters row ─────────────────────────────────────────────────── */}
      <GlassCard animate={false} className="px-4 py-3">
        <div className="flex items-center gap-3">
          {/* Search input */}
          <div className="relative flex-1">
            <input
              type="text"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(0); }}
              placeholder="Search merchant name or location…"
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-2 pl-9 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 transition-colors"
            />
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-t3 text-xs">🔍</span>
          </div>

          {/* Fraud-only toggle */}
          <button
            onClick={() => { setFraudOnly(f => !f); setPage(0); }}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium border transition-all whitespace-nowrap',
              fraudOnly
                ? 'bg-red-500/15 border-red-500/30 text-red-300'
                : 'bg-white/[0.04] border-white/[0.08] text-t3 hover:text-t2',
            )}
          >
            🚨 {fraudOnly ? 'Fraud Only (active)' : 'Show Fraud Only'}
          </button>

          {tableLoading && (
            <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
          )}
          <div className="text-[10px] text-t3 whitespace-nowrap">
            {total.toLocaleString()} transactions
          </div>
        </div>
      </GlassCard>

      {/* ── Transactions Table ────────────────────────────────────────────────── */}
      {/*
        Shows ALL bank transactions for the selected period.
        NOT filtered by customer — any transaction across the bank may appear.

        Input:  txns[] from bankTransactionsApi.list({ period })
        Output: Table with merchant, amount, location, fraud flag, date.
      */}
      <GlassCard animate={false} className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/[0.06]">
                {['Date', 'Merchant', 'Category', 'Location', 'Type', 'Amount', 'Risk', 'Flag'].map(h => (
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
                        Loading transactions…
                      </div>
                    </td>
                  </tr>
                </tbody>
              ) : (
                <motion.tbody
                  key={`${activePeriod}-${page}-${fraudOnly}-${search}`}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  className="divide-y divide-white/[0.04]"
                >
                  {txns.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-16 text-center text-sm text-t3">
                        <div className="text-2xl mb-2">↔</div>
                        No transactions found for this period
                      </td>
                    </tr>
                  ) : (
                    txns.map(tx => (
                      <tr
                        key={tx.id}
                        className={clsx(
                          'hover:bg-white/[0.02] transition-colors',
                          tx.is_flagged && 'bg-red-500/[0.03]',
                        )}
                      >
                        <td className="px-4 py-2.5 text-t3 whitespace-nowrap tabular-nums">
                          {tx.created_at ? new Date(tx.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}
                        </td>
                        <td className="px-4 py-2.5 text-t2 max-w-[160px] truncate">{tx.merchant_name || '—'}</td>
                        <td className="px-4 py-2.5 text-t3 capitalize">{tx.merchant_category || '—'}</td>
                        <td className="px-4 py-2.5 text-t3 max-w-[120px] truncate">{tx.location || '—'}</td>
                        <td className="px-4 py-2.5 capitalize text-t3">{tx.transaction_type}</td>
                        <td className={clsx(
                          'px-4 py-2.5 font-semibold tabular-nums whitespace-nowrap',
                          tx.transaction_type === 'credit' ? 'text-green-400' : 'text-red-400',
                        )}>
                          {tx.transaction_type === 'debit' ? '-' : '+'}{fmt$(tx.amount_cents)}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={clsx(
                            'text-[9px] px-1.5 py-0.5 rounded capitalize',
                            tx.merchant_risk === 'low'
                              ? 'text-green-400 bg-green-500/10'
                              : tx.merchant_risk === 'medium'
                              ? 'text-amber-400 bg-amber-500/10'
                              : 'text-red-400 bg-red-500/10',
                          )}>
                            {tx.merchant_risk}
                          </span>
                        </td>
                        <td className="px-4 py-2.5">
                          {tx.is_flagged
                            ? <span className="text-red-400 text-[10px]">🚨 fraud</span>
                            : <span className="text-t3/30 text-[10px]">—</span>}
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
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-2 py-1 rounded text-xs text-t3 disabled:opacity-30 hover:bg-white/[0.05] transition-colors"
              >
                ← Prev
              </button>
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                const start = Math.max(0, Math.min(page - 2, totalPages - 5));
                const p = start + i;
                return (
                  <button key={p} onClick={() => setPage(p)}
                    className={clsx('px-2 py-1 rounded text-xs transition-colors',
                      p === page ? 'bg-purple-500/20 text-purple-300' : 'text-t3 hover:bg-white/[0.05]'
                    )}>
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

      {/* ── Fraud Alerts Modal ──────────────────────────────────────────────── */}
      <AnimatePresence>
        {showFraudModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex flex-col bg-gray-950/95 backdrop-blur-sm overflow-hidden"
          >
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.08] bg-gray-900/80 flex-shrink-0">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-lg">🚨</span>
                <div>
                  <h2 className="text-sm font-semibold text-t1">Fraud Alerts</h2>
                  <p className="text-[10px] text-t3">
                    {fraudLoading ? 'Loading…'
                      : `${fraudTxns.length} flagged transactions · ${PERIODS.find(p => p.id === activePeriod)?.label} period · ML + rule-based detection`}
                  </p>
                </div>
                {!fraudLoading && (
                  <div className="flex gap-1.5 ml-2 flex-wrap">
                    {(['all', 'critical', 'high', 'medium', 'low'] as const).map(f => {
                      const count = f === 'all' ? fraudTxns.length
                        : fraudTxns.filter(tx => riskToSeverity(tx.merchant_risk) === f).length;
                      return (
                        <button key={f} onClick={() => setFraudFilter(f)}
                          className={clsx(
                            'px-2.5 py-1 rounded-lg text-[10px] capitalize transition-all border',
                            fraudFilter === f
                              ? 'bg-red-500/15 border-red-500/30 text-red-300'
                              : 'bg-white/[0.03] border-white/[0.06] text-t3 hover:text-t2',
                          )}>
                          {f} {count > 0 && <span className="ml-1 opacity-60">({count})</span>}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
              <button
                onClick={() => { setShowFraudModal(false); setSelectedTxn(null); }}
                className="px-3 py-2 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] text-t3 hover:text-t1 transition-all text-xs"
              >
                ✕ Close
              </button>
            </div>

            {/* Modal body */}
            <div className="flex flex-1 overflow-hidden">

              {/* ── Fraud Transaction List (left 55%) ────────────────────── */}
              <div className="w-[55%] border-r border-white/[0.06] flex flex-col overflow-hidden">
                <div className="flex-1 overflow-y-auto divide-y divide-white/[0.04]">
                  {fraudLoading ? (
                    <div className="flex items-center justify-center py-20">
                      <div className="w-6 h-6 border-2 border-red-500 border-t-transparent rounded-full animate-spin mr-2" />
                      <span className="text-xs text-t3">Loading fraud transactions…</span>
                    </div>
                  ) : fraudTxns.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 text-center">
                      <div className="text-3xl mb-3">🛡</div>
                      <p className="text-sm text-t3">No fraud transactions found for this period</p>
                    </div>
                  ) : filteredFraudTxns.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 text-center">
                      <div className="text-3xl mb-3">🔍</div>
                      <p className="text-sm text-t3">No transactions match this severity filter</p>
                    </div>
                  ) : (
                    filteredFraudTxns.map((tx, i) => {
                      const fraudType = inferFraudType(tx);
                      const info = getFraudInfo(fraudType);
                      const score = riskToScore(tx.merchant_risk);
                      const severity = riskToSeverity(tx.merchant_risk);
                      const isSelected = selectedTxn?.id === tx.id;
                      return (
                        <div
                          key={tx.id}
                          onClick={() => setSelectedTxn(tx)}
                          className={clsx(
                            'px-5 py-3.5 cursor-pointer transition-colors',
                            isSelected
                              ? 'bg-red-500/[0.08] border-l-2 border-red-500/50'
                              : 'hover:bg-white/[0.02] border-l-2 border-transparent',
                          )}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1 flex-wrap">
                                <span className="text-xs font-semibold text-t1 truncate max-w-[200px]">{info.title}</span>
                                <Badge label={severity} color={severityColor(severity)} dot />
                                <Badge label={tx.status} color={tx.status === 'completed' ? 'green' : tx.status === 'pending' ? 'amber' : 'gray'} />
                              </div>
                              <div className="text-[11px] text-t3 flex flex-wrap gap-x-3 gap-y-0.5 mb-1.5">
                                <span className="font-mono text-purple-400/80 truncate">{tx.customer_id}</span>
                                <span className={clsx('font-semibold', riskColor(score))}>
                                  Risk: {(score * 100).toFixed(0)}% ({riskLabel(score)})
                                </span>
                                <span className={tx.transaction_type === 'debit' ? 'text-red-400' : 'text-green-400'}>
                                  {tx.transaction_type === 'debit' ? '−' : '+'}{fmt$(tx.amount_cents)}
                                </span>
                              </div>
                              <div className="w-28 h-1 rounded-full bg-white/[0.06] overflow-hidden">
                                <div className={clsx('h-full rounded-full', riskBarColor(score))} style={{ width: `${score * 100}%` }} />
                              </div>
                            </div>
                            <div className="text-[10px] text-t3 flex flex-col items-end gap-0.5 flex-shrink-0">
                              <span className="text-blue-400/70 truncate max-w-[110px]">{tx.merchant_name || '—'}</span>
                              <span className="text-t3/60 truncate max-w-[110px]">{tx.location || '—'}</span>
                              <span className="text-t3/50">{new Date(tx.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* ── Transaction Detail (right 45%) ───────────────────────── */}
              <div className="w-[45%] flex flex-col overflow-hidden">
                <AnimatePresence mode="wait">
                  {selectedTxn ? (
                    <motion.div
                      key={selectedTxn.id}
                      initial={{ opacity: 0, x: 16 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0 }}
                      className="flex-1 overflow-y-auto p-5 space-y-4"
                    >
                      {(() => {
                        const tx = selectedTxn;
                        const fraudType = inferFraudType(tx);
                        const info = getFraudInfo(fraudType);
                        const score = riskToScore(tx.merchant_risk);
                        const severity = riskToSeverity(tx.merchant_risk);
                        return (
                          <>
                            {/* Header */}
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-[10px] font-mono text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded">{tx.id}</span>
                              <Badge label={severity} color={severityColor(severity)} dot />
                              <Badge label={tx.status} color={tx.status === 'completed' ? 'green' : 'amber'} />
                            </div>

                            {/* Title */}
                            <h3 className="text-base font-bold text-t1">{info.title}</h3>

                            {/* Risk score meter */}
                            <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                              <div className="text-[10px] text-t3 uppercase tracking-wider mb-2">ML Fraud Risk Score</div>
                              <div className={clsx('text-2xl font-bold', riskColor(score))}>
                                {(score * 100).toFixed(0)}%
                                <span className="text-sm font-normal ml-2 text-t2">{riskLabel(score)} Risk</span>
                              </div>
                              <div className="w-full h-2 rounded-full bg-white/[0.06] mt-2.5 overflow-hidden">
                                <motion.div
                                  initial={{ width: 0 }}
                                  animate={{ width: `${score * 100}%` }}
                                  transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
                                  className={clsx('h-full rounded-full', riskBarColor(score))}
                                />
                              </div>
                              <div className="text-[10px] text-t3 mt-2">Detection: ML model + Rule-based transaction monitoring</div>
                            </div>

                            {/* Explanation */}
                            <div className="p-4 rounded-xl bg-blue-500/[0.04] border border-blue-500/[0.12]">
                              <div className="flex items-center gap-1.5 mb-2">
                                <span className="text-xs">📋</span>
                                <span className="text-[10px] text-blue-400 uppercase tracking-wider font-medium">Explanation</span>
                              </div>
                              <p className="text-xs text-t2 leading-relaxed">{info.explanation}</p>
                            </div>

                            {/* Trigger reasons */}
                            <div className="p-4 rounded-xl bg-amber-500/[0.04] border border-amber-500/[0.12]">
                              <div className="flex items-center gap-1.5 mb-2.5">
                                <span className="text-xs">⚠</span>
                                <span className="text-[10px] text-amber-400 uppercase tracking-wider font-medium">Alert Trigger Reasons</span>
                              </div>
                              <ul className="space-y-1.5">
                                {info.triggers.map((trigger, ti) => (
                                  <li key={ti} className="flex items-start gap-2 text-xs text-t2">
                                    <span className="text-amber-500/60 mt-0.5 flex-shrink-0">›</span>
                                    <span className="leading-relaxed">{trigger}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>

                            {/* Transaction metadata */}
                            <div className="rounded-xl bg-white/[0.02] border border-white/[0.06] overflow-hidden">
                              {[
                                { label: 'Transaction ID', value: tx.id },
                                { label: 'Customer ID',    value: tx.customer_id },
                                { label: 'Amount',         value: `${tx.transaction_type === 'debit' ? '−' : '+'}${fmt$(tx.amount_cents)}` },
                                { label: 'Type',           value: tx.transaction_type },
                                { label: 'Status',         value: tx.status },
                                { label: 'Merchant',       value: tx.merchant_name || '—' },
                                { label: 'Category',       value: tx.merchant_category || '—' },
                                { label: 'Location',       value: tx.location || '—' },
                                { label: 'Channel',        value: tx.channel || '—' },
                                { label: 'Detected',       value: new Date(tx.created_at).toLocaleString() },
                              ].map((row, ri) => (
                                <div key={row.label}
                                  className={clsx('flex justify-between items-center px-4 py-2.5 text-xs', ri > 0 && 'border-t border-white/[0.04]')}>
                                  <span className="text-t3">{row.label}</span>
                                  <span className="text-t1 font-medium text-right max-w-[55%] break-all">{row.value}</span>
                                </div>
                              ))}
                            </div>

                            {/* Description if present */}
                            {tx.description && tx.description !== tx.merchant_name && (
                              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.04]">
                                <div className="text-[10px] text-t3 mb-1">Description</div>
                                <p className="text-xs text-t2">{tx.description}</p>
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </motion.div>
                  ) : (
                    <motion.div
                      key="empty"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="flex-1 flex flex-col items-center justify-center text-center p-10"
                    >
                      <div className="text-4xl mb-4">🛡</div>
                      <p className="text-sm font-medium text-t2 mb-2">Select a transaction to view details</p>
                      <p className="text-xs text-t3 leading-relaxed max-w-xs">
                        Each entry shows the fraud type, explanation, trigger reasons, risk score, and full transaction metadata.
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

            </div>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
}
