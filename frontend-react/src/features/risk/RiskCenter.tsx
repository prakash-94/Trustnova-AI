import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
} from 'recharts';
import { riskApi } from '@/services/api';
import GlassCard from '@/components/common/GlassCard';
import Badge from '@/components/common/Badge';
import type { CustomerSummary } from '@/types';
import type { NavSection } from '@/components/layout/Sidebar';

const BAND_FILL: Record<string, string> = {
  low:      '#22c55e',
  medium:   '#3b82f6',
  high:     '#f59e0b',
  critical: '#ef4444',
};

function RiskTooltip({ active, payload }: { active?: boolean; payload?: { name: string; value: number; payload: { pct: number; label: string } }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0];
  return (
    <div className="bg-[#0f0f1a] border border-white/[0.08] rounded-xl px-3 py-2 text-xs shadow-xl">
      <div className="font-semibold text-t1 mb-0.5">{d.payload.label} Risk</div>
      <div className="text-purple-300 font-bold">{d.value.toLocaleString()} customers</div>
      <div className="text-t3">{d.payload.pct.toFixed(1)}% of portfolio</div>
    </div>
  );
}

interface SegmentCustomer {
  customer_id: string;
  name: string;
  email: string;
  credit_score: number;
  risk_level: string;
  account_type: string;
  income: number;
  balance: number;
  fraud_alert_count: number;
}

interface RiskCenterProps {
  customer?: CustomerSummary | null;
  onSelectCustomer?: (c: CustomerSummary) => void;
  onNavigate?: (tab: NavSection) => void;
}

export default function RiskCenter({ customer: _customer, onSelectCustomer, onNavigate }: RiskCenterProps) {
  const [portfolio, setPortfolio] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeBand, setActiveBand] = useState<string | null>(null);
  const [segmentCustomers, setSegmentCustomers] = useState<SegmentCustomer[]>([]);
  const [segmentTotal, setSegmentTotal] = useState(0);
  const [segmentLoading, setSegmentLoading] = useState(false);

  useEffect(() => {
    riskApi.portfolio().then(setPortfolio).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const handleSegmentClick = async (band: string) => {
    if (activeBand === band) {
      setActiveBand(null);
      setSegmentCustomers([]);
      return;
    }
    setActiveBand(band);
    setSegmentLoading(true);
    try {
      const res = await riskApi.segment(band, 50, 0);
      setSegmentCustomers(res.customers as unknown as SegmentCustomer[]);
      setSegmentTotal(res.total);
    } catch { /* */ } finally {
      setSegmentLoading(false);
    }
  };

  const dist = (portfolio?.risk_distribution as Record<string, { count: number; pct: number }>) ?? {};

  const BAND_META: Record<string, { color: string; label: string; desc: string; tooltip: string }> = {
    low:      { color: 'green',  label: 'Low',      desc: 'Score 80–100', tooltip: 'Excellent credit profile. Standard monitoring, no additional controls.' },
    medium:   { color: 'blue',   label: 'Medium',   desc: 'Score 60–79',  tooltip: 'Acceptable risk. Standard procedures. Quarterly review.' },
    high:     { color: 'amber',  label: 'High',     desc: 'Score 40–59',  tooltip: 'Elevated risk. Enhanced monitoring. Monthly review + manager sign-off.' },
    critical: { color: 'red',    label: 'Critical', desc: 'Score 0–39',   tooltip: 'Significant risk. EDD required. Immediate escalation to Compliance.' },
  };

  return (
    <div className="space-y-4">
      {/* Purpose Banner */}
      <GlassCard animate={false} className="px-5 py-4">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-base flex-shrink-0">
            📊
          </div>
          <div>
            <h2 className="text-sm font-semibold text-t1 mb-1">Risk Center — Portfolio Risk Intelligence</h2>
            <p className="text-xs text-t3 leading-relaxed max-w-3xl">
              Monitors <strong className="text-t2">portfolio-level</strong> credit, market, and operational risk across all customers.
              Click any risk band row to drill into the customers in that segment.
              Risk bands are derived from credit scores, payment history, AML ratings, and KYC status.
            </p>
          </div>
        </div>
      </GlassCard>

      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Avg Credit Score',   value: (portfolio?.avg_credit_score as number)?.toLocaleString() ?? '—', color: 'green',
            tooltip: 'Mean FICO credit score across all 1,000 customers in the database' },
          { label: 'Total Customers',    value: (portfolio?.total_customers as number)?.toLocaleString() ?? '—',  color: 'blue',
            tooltip: 'Total number of active customer accounts in the core banking system' },
          { label: 'NPL Ratio',          value: `${portfolio?.npls_pct ?? '—'}%`,                                 color: 'amber',
            tooltip: 'Non-Performing Loans: loans 90+ days past due as a % of total loan book. Regulatory threshold: < 5%' },
          { label: 'Provision Coverage', value: `${portfolio?.provision_coverage_pct ?? '—'}%`,                   color: 'purple',
            tooltip: 'Loan loss reserves ÷ NPL balance. > 100% means reserves exceed non-performing exposure — well-capitalized.' },
        ].map((m, i) => (
          <GlassCard key={m.label} delay={i * 0.06} className="p-4 group relative">
            <div className={`text-2xl font-bold tabular-nums text-${m.color}-400 mb-0.5`}>{loading ? '…' : m.value}</div>
            <div className="text-xs text-t3 uppercase tracking-wider">{m.label}</div>
            <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block w-56 px-2 py-1.5 rounded-lg bg-gray-900 border border-white/[0.08] text-[10px] text-t2 z-10 shadow-lg leading-relaxed">
              {m.tooltip}
            </div>
          </GlassCard>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4 items-start">
        {/* Risk Distribution — Pie chart */}
        <GlassCard animate={false} className="p-5">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-sm font-semibold text-t1">Portfolio Risk Distribution</h2>
              <p className="text-[10px] text-t3 mt-0.5">Click a segment to drill into customers</p>
            </div>
            {activeBand && (
              <button onClick={() => { setActiveBand(null); setSegmentCustomers([]); }}
                className="text-[10px] text-t3 hover:text-red-400 transition-colors px-2 py-1 rounded-lg border border-white/[0.06]">
                ✕ clear
              </button>
            )}
          </div>
          {loading ? (
            <div className="flex justify-center py-16">
              <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (() => {
            const pieData = Object.entries(dist)
              .filter(([, s]) => s.count > 0)
              .map(([band, s]) => ({
                band,
                label: BAND_META[band]?.label ?? band,
                value: s.count,
                pct:   s.pct,
              }));
            const total = pieData.reduce((a, d) => a + d.value, 0);
            return (
              <div className="flex items-center gap-6">
                {/* Donut with center label */}
                <div className="relative flex-shrink-0" style={{ width: 200, height: 200 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%" cy="50%"
                        innerRadius={62} outerRadius={90}
                        paddingAngle={2}
                        dataKey="value"
                        nameKey="label"
                        onClick={(entry) => handleSegmentClick((entry as unknown as { band: string }).band)}
                        style={{ cursor: 'pointer' }}
                        stroke="none"
                        startAngle={90}
                        endAngle={-270}
                      >
                        {pieData.map((entry) => (
                          <Cell
                            key={entry.band}
                            fill={BAND_FILL[entry.band] ?? '#888'}
                            opacity={activeBand === null || activeBand === entry.band ? 0.9 : 0.18}
                          />
                        ))}
                      </Pie>
                      <Tooltip content={<RiskTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  {/* Center text */}
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                    <div className="text-2xl font-bold text-t1 tabular-nums">{total.toLocaleString()}</div>
                    <div className="text-[10px] text-t3 uppercase tracking-wider">Customers</div>
                  </div>
                </div>

                {/* Legend */}
                <div className="flex-1 space-y-2.5">
                  {pieData.map((entry) => {
                    const isActive = activeBand === entry.band;
                    const fill = BAND_FILL[entry.band] ?? '#888';
                    return (
                      <button key={entry.band} onClick={() => handleSegmentClick(entry.band)}
                        className={`w-full group flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all text-left
                          ${isActive
                            ? 'border border-white/[0.12] bg-white/[0.06]'
                            : 'border border-transparent hover:border-white/[0.06] hover:bg-white/[0.03]'}`}>
                        {/* Color swatch */}
                        <div className="w-3.5 h-3.5 rounded flex-shrink-0 transition-transform group-hover:scale-110"
                          style={{ background: fill, boxShadow: isActive ? `0 0 8px ${fill}80` : undefined }} />

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-1">
                            <span className={`text-xs font-semibold ${isActive ? 'text-t1' : 'text-t2'}`}>
                              {entry.label}
                            </span>
                            <span className="text-xs font-bold tabular-nums" style={{ color: fill }}>
                              {entry.pct.toFixed(1)}%
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] text-t3 tabular-nums">
                              {entry.value.toLocaleString()} customers
                            </span>
                            {isActive && (
                              <span className="text-[9px] text-purple-400 font-medium">viewing ▾</span>
                            )}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })()}
        </GlassCard>

        {/* Key Portfolio Metrics */}
        <GlassCard animate={false} className="p-5">
          <h2 className="text-sm font-semibold text-t1 mb-4">Key Portfolio Metrics</h2>
          {loading ? (
            <div className="flex justify-center py-8">
              <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="space-y-3">
              {[
                { label: 'Average Credit Score',  value: String(portfolio?.avg_credit_score ?? '—'),
                  hint: 'Mean FICO across all active customers' },
                { label: 'Non-Performing Loans',  value: `${portfolio?.npls_pct ?? '—'}%`,
                  hint: 'Loans 90+ days past due — regulatory threshold is 5%' },
                { label: 'Provision Coverage',    value: `${portfolio?.provision_coverage_pct ?? '—'}%`,
                  hint: 'Loan loss reserves ÷ NPL balance (>100% = well-capitalized)' },
                { label: 'Open Fraud Alerts',     value: String((portfolio?.fraud_alerts as Record<string, number>)?.open ?? '—'),
                  hint: 'Active fraud investigations from the fraud_alerts table' },
                { label: 'Total Fraud Alerts',    value: String((portfolio?.fraud_alerts as Record<string, number>)?.total ?? '—'),
                  hint: 'All fraud alerts including resolved and closed' },
                { label: 'High Risk Customers',   value: dist.high?.count?.toLocaleString() ?? '—',
                  hint: 'Customers in High band — credit score 40–59 composite risk' },
                { label: 'Critical Risk',         value: dist.critical?.count?.toLocaleString() ?? '—',
                  hint: 'Customers requiring immediate escalation to Compliance' },
              ].map(row => (
                <div key={row.label} className="flex justify-between py-2 border-b border-white/[0.04] text-xs group">
                  <div>
                    <div className="text-t3">{row.label}</div>
                    <div className="text-[10px] text-t3/50 opacity-0 group-hover:opacity-100 transition-opacity">{row.hint}</div>
                  </div>
                  <span className="text-t1 font-medium">{row.value}</span>
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      </div>

      {/* Segment drill-down panel */}
      <AnimatePresence>
        {activeBand && (
          <motion.div
            key={activeBand}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3 }}
            className="overflow-hidden"
          >
            <GlassCard animate={false} className="overflow-hidden">
              <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-t1">
                    {BAND_META[activeBand]?.label} Risk Segment — {segmentTotal.toLocaleString()} customers
                  </h3>
                  <p className="text-xs text-t3">Sorted by credit score (lowest first) · {BAND_META[activeBand]?.tooltip}</p>
                </div>
                <button onClick={() => { setActiveBand(null); setSegmentCustomers([]); }}
                  className="text-xs text-t3 hover:text-red-400 transition-colors px-2 py-1 rounded-lg border border-white/[0.06]">
                  ✕ close
                </button>
              </div>

              {segmentLoading ? (
                <div className="flex justify-center py-10">
                  <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.06]">
                        {['Customer ID', 'Name', 'Email', 'Credit Score', 'Risk Level', 'Account Type', 'Balance', 'Fraud Alerts'].map(h => (
                          <th key={h} className="px-4 py-2 text-left text-[10px] text-t3 uppercase tracking-wider font-medium whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.04]">
                      {segmentCustomers.map((c, i) => (
                        <motion.tr key={c.customer_id}
                          initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}
                          onClick={() => {
                            onSelectCustomer?.({ customer_id: c.customer_id, name: c.name, email: c.email });
                            onNavigate?.('customer_search');
                          }}
                          className={`transition-colors group ${onSelectCustomer ? 'cursor-pointer hover:bg-purple-500/[0.08]' : 'hover:bg-white/[0.02]'}`}>
                          <td className="px-4 py-2.5 font-mono text-purple-400 underline underline-offset-2 decoration-purple-400/30">{c.customer_id}</td>
                          <td className="px-4 py-2.5 text-t1 font-medium">{c.name}</td>
                          <td className="px-4 py-2.5 text-t3">{c.email}</td>
                          <td className="px-4 py-2.5">
                            <span className={c.credit_score >= 720 ? 'text-green-400' : c.credit_score >= 640 ? 'text-amber-400' : 'text-red-400'}>
                              {c.credit_score}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 relative">
                            <Badge label={c.risk_level} color={
                              ({ Low: 'green', Medium: 'amber', High: 'red', 'Very High': 'red' } as Record<string, 'green' | 'amber' | 'red' | 'gray'>)[c.risk_level] ?? 'gray'
                            } />
                            {/* Risk reason tooltip */}
                            <div className="absolute left-0 top-full mt-1 z-50 hidden group-hover:block w-56 bg-[#0f0f1a] border border-white/[0.12] rounded-xl shadow-2xl p-3 pointer-events-none">
                              <p className="text-[9px] text-t3 uppercase tracking-widest mb-2">Risk Factors</p>
                              <div className="space-y-1.5">
                                <div className="flex justify-between text-[10px]">
                                  <span className="text-t3">AML Rating</span>
                                  <span className={({ Low: 'text-green-400', Medium: 'text-amber-400', High: 'text-red-400', 'Very High': 'text-red-400' } as Record<string, string>)[c.risk_level] ?? 'text-t2'}>{c.risk_level}</span>
                                </div>
                                <div className="flex justify-between text-[10px]">
                                  <span className="text-t3">Credit Score</span>
                                  <span className={c.credit_score >= 720 ? 'text-green-400' : c.credit_score >= 640 ? 'text-amber-400' : 'text-red-400'}>
                                    {c.credit_score} — {c.credit_score >= 720 ? 'Good' : c.credit_score >= 640 ? 'Fair' : 'Poor'}
                                  </span>
                                </div>
                                <div className="flex justify-between text-[10px]">
                                  <span className="text-t3">Fraud Alerts</span>
                                  <span className={c.fraud_alert_count > 2 ? 'text-red-400' : c.fraud_alert_count > 0 ? 'text-amber-400' : 'text-green-400'}>
                                    {c.fraud_alert_count} {c.fraud_alert_count > 2 ? '— elevated' : c.fraud_alert_count > 0 ? '— watch' : '— clean'}
                                  </span>
                                </div>
                                <div className="flex justify-between text-[10px]">
                                  <span className="text-t3">Account Type</span>
                                  <span className="text-t2 capitalize">{c.account_type?.replace(/_/g, ' ')}</span>
                                </div>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-2.5 text-t2 capitalize">{c.account_type?.replace(/_/g, ' ')}</td>
                          <td className="px-4 py-2.5 text-t2">
                            ${c.balance?.toLocaleString('en-US', { maximumFractionDigits: 0 }) ?? '—'}
                          </td>
                          <td className="px-4 py-2.5">
                            {c.fraud_alert_count > 0
                              ? <span className="text-red-400 font-medium">{c.fraud_alert_count}</span>
                              : <span className="text-green-400/60">0</span>}
                          </td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                  {segmentTotal > segmentCustomers.length && (
                    <div className="px-5 py-3 text-center text-xs text-t3 border-t border-white/[0.04]">
                      Showing {segmentCustomers.length} of {segmentTotal} customers in this segment
                    </div>
                  )}
                </div>
              )}
            </GlassCard>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Risk Rating Framework */}
      <GlassCard animate={false} className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-t1">Risk Rating Framework</h2>
          <span className="text-[10px] text-t3">How composite risk scores are calculated — hover for details</span>
        </div>
        <div className="grid grid-cols-4 gap-3">
          {Object.entries(BAND_META).map(([band, meta]) => {
            const stats = dist[band];
            return (
              <motion.div key={band} whileHover={{ y: -2 }}
                className={`p-3 rounded-xl bg-${meta.color}-500/[0.08] border border-${meta.color}-500/20 cursor-pointer`}
                onClick={() => handleSegmentClick(band)}>
                <Badge label={meta.label} color={meta.color as 'green' | 'blue' | 'amber' | 'red'} className="mb-2" />
                <div className={`text-xs font-mono text-${meta.color}-400 mb-1.5`}>{meta.desc}</div>
                {stats && (
                  <div className="text-[10px] text-t3 mb-1.5">
                    {stats.count.toLocaleString()} customers ({stats.pct.toFixed(1)}%)
                  </div>
                )}
                <p className="text-[10px] text-t3 leading-relaxed">{meta.tooltip}</p>
                <div className={`mt-2 text-[10px] text-${meta.color}-400/70`}>Click to view customers →</div>
              </motion.div>
            );
          })}
        </div>
      </GlassCard>
    </div>
  );
}
