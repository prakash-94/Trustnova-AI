import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { kpiApi, fraudApi, loansApi, customersApi, type KpiStats } from '@/services/api';
import GlassCard from '@/components/common/GlassCard';
import type { NavSection } from '@/components/layout/Sidebar';

interface Props {
  role: string;
  roleLabel: string;
  onNavigate: (tab: NavSection) => void;
  onAddCustomer: () => void;
  onOpenFraud?: () => void;
  onOpenCustomers?: () => void;
  onOpenDocs?: () => void;
  onOpenAITrust?: () => void;
  refreshKey?: number;
}

// KPI keys that open a modal or navigate when clicked
const KEY_ACTIONS: Partial<Record<keyof KpiStats, 'fraud' | 'customers' | 'docs' | 'trust' | 'nav'>> = {
  total_customers:    'customers',
  fraud_open:         'fraud',
  fraud_total:        'fraud',
  fraud_critical:     'fraud',
  trust_score_avg:    'trust',
  docs_indexed:       'docs',
  loan_count:         'nav',
  loan_pending:       'nav',
  kyc_pending:        'nav',
  aml_open:           'nav',
  avg_credit_score:   'nav',
  high_risk_customers:'nav',
  ai_queries_today:   'nav',
};

const KEY_NAV_TARGET: Partial<Record<keyof KpiStats, NavSection>> = {
  loan_count:          'loans',
  loan_pending:        'loans',
  kyc_pending:         'kyc_center',
  aml_open:            'aml_center',
  avg_credit_score:    'risk_center',
  high_risk_customers: 'risk_center',
  ai_queries_today:    'ai_copilot',
};

// Role → dashboard config
const ROLE_CONFIG: Record<string, {
  title: string;
  description: string;
  color: string;
  icon: string;
  kpis: { key: keyof KpiStats; label: string; icon: string; color: string; onClick?: string }[];
  quickLinks: { label: string; icon: string; tab: NavSection; desc: string }[];
}> = {
  admin: {
    title: 'Administrator Overview',
    description: 'Full platform visibility — all metrics, all roles, all systems.',
    color: 'from-purple-500 to-blue-600',
    icon: '⚙',
    kpis: [
      { key: 'total_customers',    label: 'Total Customers',     icon: '👥', color: 'text-blue-400'   },
      { key: 'fraud_open',         label: 'Open Fraud Alerts',   icon: '🛡', color: 'text-red-400'    },
      { key: 'loan_count',         label: 'Total Loans',         icon: '📋', color: 'text-amber-400'  },
      { key: 'ai_queries_today',   label: 'AI Queries Today',    icon: '⚡', color: 'text-purple-400' },
      { key: 'high_risk_customers',label: 'High Risk Customers', icon: '⚠', color: 'text-orange-400' },
      { key: 'trust_score_avg',    label: 'Trust Score Avg',     icon: '✦', color: 'text-green-400'  },
      { key: 'docs_indexed',       label: 'Policy Documents',    icon: '📄', color: 'text-cyan-400'   },
    ],
    quickLinks: [
      { label: 'Customer 360', icon: '👤', tab: 'customer_search', desc: 'View & manage all customers' },
      { label: 'Fraud Center', icon: '🛡', tab: 'fraud_center', desc: 'Investigate fraud alerts' },
      { label: 'AML Center', icon: '🔎', tab: 'aml_center', desc: 'Anti-money laundering cases' },
      { label: 'KYC Center', icon: '🪪', tab: 'kyc_center', desc: 'Identity verification queue' },
      { label: 'Risk Center', icon: '📊', tab: 'risk_center', desc: 'Risk scoring & analysis' },
      { label: 'AI Copilot', icon: '✦', tab: 'ai_copilot', desc: 'Chat with banking AI' },
    ],
  },
  fraud_analyst: {
    title: 'Fraud Analyst Dashboard',
    description: 'Monitor, investigate, and resolve fraud alerts across all accounts.',
    color: 'from-red-500 to-orange-600',
    icon: '🛡',
    kpis: [
      { key: 'fraud_total', label: 'Total Alerts', icon: '🛡', color: 'text-red-400' },
      { key: 'fraud_open', label: 'Open Alerts', icon: '🔴', color: 'text-red-400' },
      { key: 'fraud_critical', label: 'Critical (≥85%)', icon: '🚨', color: 'text-orange-400' },
      { key: 'ai_queries_today', label: 'AI Queries Today', icon: '⚡', color: 'text-purple-400' },
    ],
    quickLinks: [
      { label: 'Fraud Center', icon: '🛡', tab: 'fraud_center', desc: 'All fraud alerts & cases' },
      { label: 'Customer Search', icon: '👤', tab: 'customer_search', desc: 'Look up customers' },
      { label: 'Risk Center', icon: '📊', tab: 'risk_center', desc: 'Risk scoring details' },
      { label: 'AI Copilot', icon: '✦', tab: 'ai_copilot', desc: 'Investigate with AI assistance' },
    ],
  },
  aml_analyst: {
    title: 'AML Analyst Dashboard',
    description: 'BSA/AML monitoring — suspicious activity, SAR filing, OFAC screening.',
    color: 'from-amber-500 to-yellow-600',
    icon: '🔎',
    kpis: [
      { key: 'aml_open', label: 'Open AML Cases', icon: '🔎', color: 'text-amber-400' },
      { key: 'high_risk_customers', label: 'High Risk Customers', icon: '⚠', color: 'text-red-400' },
      { key: 'total_customers', label: 'Total Customers', icon: '👥', color: 'text-blue-400' },
      { key: 'ai_queries_today', label: 'AI Queries Today', icon: '⚡', color: 'text-purple-400' },
    ],
    quickLinks: [
      { label: 'AML Center', icon: '🔎', tab: 'aml_center', desc: 'AML cases & SAR filing' },
      { label: 'Customer Search', icon: '👤', tab: 'customer_search', desc: 'KYC & risk profile lookup' },
      { label: 'Risk Center', icon: '📊', tab: 'risk_center', desc: 'Risk band analysis' },
      { label: 'AI Copilot', icon: '✦', tab: 'ai_copilot', desc: 'AML policy guidance' },
    ],
  },
  loan_officer: {
    title: 'Loan Officer Dashboard',
    description: 'Manage loan applications, underwriting pipeline, and approval decisions.',
    color: 'from-green-500 to-teal-600',
    icon: '📋',
    kpis: [
      { key: 'loan_count', label: 'Total Loans', icon: '📋', color: 'text-green-400' },
      { key: 'loan_pending', label: 'Pending Review', icon: '⏳', color: 'text-amber-400' },
      { key: 'avg_credit_score', label: 'Avg Credit Score', icon: '💳', color: 'text-blue-400' },
      { key: 'ai_queries_today', label: 'AI Queries Today', icon: '⚡', color: 'text-purple-400' },
    ],
    quickLinks: [
      { label: 'Loans', icon: '📋', tab: 'loans', desc: 'Loan pipeline & approvals' },
      { label: 'Customer Search', icon: '👤', tab: 'customer_search', desc: 'Customer credit profiles' },
      { label: 'Risk Center', icon: '📊', tab: 'risk_center', desc: 'Credit risk scores' },
      { label: 'AI Copilot', icon: '✦', tab: 'ai_copilot', desc: 'Loan policy & eligibility' },
    ],
  },
  kyc_analyst: {
    title: 'KYC Analyst Dashboard',
    description: 'Identity verification queue, document review, and compliance checks.',
    color: 'from-cyan-500 to-blue-600',
    icon: '🪪',
    kpis: [
      { key: 'kyc_pending', label: 'KYC Pending', icon: '🪪', color: 'text-amber-400' },
      { key: 'total_customers', label: 'Total Customers', icon: '👥', color: 'text-blue-400' },
      { key: 'high_risk_customers', label: 'Enhanced Due Diligence', icon: '⚠', color: 'text-red-400' },
      { key: 'ai_queries_today', label: 'AI Queries Today', icon: '⚡', color: 'text-purple-400' },
    ],
    quickLinks: [
      { label: 'KYC Center', icon: '🪪', tab: 'kyc_center', desc: 'Verification queue & docs' },
      { label: 'Customer Search', icon: '👤', tab: 'customer_search', desc: 'Customer identity details' },
      { label: 'Risk Center', icon: '📊', tab: 'risk_center', desc: 'Risk assessment' },
      { label: 'AI Copilot', icon: '✦', tab: 'ai_copilot', desc: 'KYC policy guidance' },
    ],
  },
  personal_banker: {
    title: 'Personal Banker Dashboard',
    description: 'Customer portfolio management, account servicing, and relationship tools.',
    color: 'from-purple-500 to-indigo-600',
    icon: '👤',
    kpis: [
      { key: 'total_customers', label: 'Total Customers', icon: '👥', color: 'text-blue-400' },
      { key: 'kyc_pending', label: 'Pending KYC', icon: '🪪', color: 'text-amber-400' },
      { key: 'trust_score_avg', label: 'Trust Score Avg', icon: '✦', color: 'text-green-400' },
      { key: 'ai_queries_today', label: 'AI Queries Today', icon: '⚡', color: 'text-purple-400' },
    ],
    quickLinks: [
      { label: 'Customer Search', icon: '👤', tab: 'customer_search', desc: 'Full customer 360 view' },
      { label: 'Credit Cards', icon: '💳', tab: 'credit_cards', desc: 'Submit card applications' },
      { label: 'KYC Center', icon: '🪪', tab: 'kyc_center', desc: 'Verification status' },
      { label: 'AI Copilot', icon: '✦', tab: 'ai_copilot', desc: 'Customer intelligence' },
    ],
  },
  branch_manager: {
    title: 'Branch Manager Dashboard',
    description: 'Branch-wide metrics, customer portfolio health, and compliance overview.',
    color: 'from-indigo-500 to-purple-600',
    icon: '🏦',
    kpis: [
      { key: 'total_customers', label: 'Total Customers', icon: '👥', color: 'text-blue-400' },
      { key: 'fraud_open', label: 'Open Fraud Alerts', icon: '🛡', color: 'text-red-400' },
      { key: 'loan_pending', label: 'Loans Pending', icon: '📋', color: 'text-amber-400' },
      { key: 'trust_score_avg', label: 'Trust Score Avg', icon: '✦', color: 'text-green-400' },
    ],
    quickLinks: [
      { label: 'Customer Search', icon: '👤', tab: 'customer_search', desc: 'Full customer view' },
      { label: 'Credit Cards', icon: '💳', tab: 'credit_cards', desc: 'Review card applications' },
      { label: 'Loans', icon: '📋', tab: 'loans', desc: 'Loan pipeline' },
      { label: 'AI Copilot', icon: '✦', tab: 'ai_copilot', desc: 'Branch intelligence' },
    ],
  },
  executive: {
    title: 'Executive Dashboard',
    description: 'Strategic overview — customer intelligence, AI copilot, and appointment management.',
    color: 'from-amber-500 to-orange-600',
    icon: '🏛',
    kpis: [
      { key: 'total_customers', label: 'Total Customers', icon: '👥', color: 'text-blue-400' },
      { key: 'loan_count', label: 'Total Loans', icon: '📋', color: 'text-amber-400' },
      { key: 'trust_score_avg', label: 'Trust Score Avg', icon: '✦', color: 'text-green-400' },
      { key: 'ai_queries_today', label: 'AI Queries Today', icon: '⚡', color: 'text-purple-400' },
    ],
    quickLinks: [
      { label: 'Customer Search', icon: '👤', tab: 'customer_search', desc: 'Customer profiles & 360 view' },
      { label: 'Appointments', icon: '📅', tab: 'appointments', desc: 'Schedule & manage meetings' },
      { label: 'Credit Cards', icon: '💳', tab: 'credit_cards', desc: 'Submit card applications' },
      { label: 'AI Copilot', icon: '✦', tab: 'ai_copilot', desc: 'Executive intelligence' },
    ],
  },
  credit_risk_analyst: {
    title: 'Credit Risk Analyst Dashboard',
    description: 'Credit portfolio risk, scoring models, and regulatory capital analysis.',
    color: 'from-orange-500 to-red-600',
    icon: '📊',
    kpis: [
      { key: 'avg_credit_score', label: 'Avg Credit Score', icon: '💳', color: 'text-blue-400' },
      { key: 'high_risk_customers', label: 'High Risk Customers', icon: '⚠', color: 'text-red-400' },
      { key: 'loan_count', label: 'Active Loans', icon: '📋', color: 'text-amber-400' },
      { key: 'ai_queries_today', label: 'AI Queries Today', icon: '⚡', color: 'text-purple-400' },
    ],
    quickLinks: [
      { label: 'Risk Center', icon: '📊', tab: 'risk_center', desc: 'Risk scoring & bands' },
      { label: 'Loans', icon: '📋', tab: 'loans', desc: 'Loan portfolio analysis' },
      { label: 'Customer Search', icon: '👤', tab: 'customer_search', desc: 'Individual risk profiles' },
      { label: 'AI Copilot', icon: '✦', tab: 'ai_copilot', desc: 'Risk policy & models' },
    ],
  },
  treasury_analyst: {
    title: 'Treasury Analyst Dashboard',
    description: 'Liquidity management, cash flows, Basel III ratios, and reserve positions.',
    color: 'from-teal-500 to-green-600',
    icon: '💰',
    kpis: [
      { key: 'trust_score_avg', label: 'Trust Score Avg', icon: '✦', color: 'text-green-400' },
      { key: 'docs_indexed', label: 'Policy Docs', icon: '📄', color: 'text-blue-400' },
      { key: 'ai_queries_today', label: 'AI Queries Today', icon: '⚡', color: 'text-purple-400' },
      { key: 'loan_count', label: 'Active Loans', icon: '📋', color: 'text-amber-400' },
    ],
    quickLinks: [
      { label: 'Treasury', icon: '💰', tab: 'treasury_dashboard', desc: 'Liquidity & reserve position' },
      { label: 'Transactions', icon: '↔', tab: 'transactions', desc: 'Cash flow analysis' },
      { label: 'AI Copilot', icon: '✦', tab: 'ai_copilot', desc: 'Treasury policy guidance' },
      { label: 'Compliance', icon: '⚖', tab: 'compliance_center', desc: 'Regulatory reporting' },
    ],
  },
};

const DEFAULT_CONFIG = ROLE_CONFIG.personal_banker;

function getConfig(role: string) {
  return ROLE_CONFIG[role] ?? DEFAULT_CONFIG;
}

function fmtVal(key: keyof KpiStats, stats: KpiStats): string {
  const v = stats[key];
  if (v === undefined || v === null) return '—';
  if (key === 'trust_score_avg') return v.toFixed(1);
  if (key === 'avg_credit_score') return v.toLocaleString();
  return Number(v).toLocaleString();
}

export default function RoleDashboard({ role, roleLabel, onNavigate, onAddCustomer, onOpenFraud, onOpenCustomers, onOpenDocs, onOpenAITrust, refreshKey = 0 }: Props) {
  const [stats, setStats] = useState<KpiStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [kpiError, setKpiError] = useState(false);
  const cfg = getConfig(role);
  const [recentItems, setRecentItems] = useState<Array<{id: string; title: string; sub: string; badge?: string; badgeColor?: string; onClick?: () => void}>>([]);
  const [recentLoading, setRecentLoading] = useState(true);
  const [recentLabel, setRecentLabel] = useState('Recent Activity');

  const loadKpi = () => {
    setLoading(true);
    setKpiError(false);
    kpiApi.stats()
      .then(data => { setStats(data); setKpiError(false); })
      .catch(() => setKpiError(true))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadKpi(); }, [refreshKey]);

  useEffect(() => {
    setRecentLoading(true);
    const roleKey = role;

    if (roleKey === 'fraud_analyst' || roleKey === 'admin') {
      setRecentLabel('Recent Fraud Alerts');
      fraudApi.list({ limit: 5 }).then(r => {
        setRecentItems((r.alerts as Array<{alert_id?: string; id?: string; fraud_type?: string; customer_id?: string; status?: string; severity?: string}>).slice(0, 5).map(a => ({
          id: String(a.alert_id ?? a.id ?? ''),
          title: String(a.fraud_type ?? 'Unknown').replace(/_/g, ' '),
          sub: `Customer ${String(a.customer_id ?? '').slice(0, 8)}`,
          badge: String(a.status ?? 'open'),
          badgeColor: a.status === 'open' ? 'text-red-400 bg-red-500/10' : a.status === 'under_review' ? 'text-amber-400 bg-amber-500/10' : 'text-green-400 bg-green-500/10',
          onClick: () => onNavigate('fraud_center'),
        })));
      }).catch(() => setRecentItems([])).finally(() => setRecentLoading(false));
    } else if (roleKey === 'loan_officer' || roleKey === 'credit_risk_analyst') {
      setRecentLabel('Pending Loans');
      loansApi.list('pending', undefined, 5).then(r => {
        setRecentItems((r.loans ?? []).slice(0, 5).map((l: {id?: string; loan_type?: string; customer_id?: string; requested_amount_cents?: number}) => ({
          id: String(l.id ?? ''),
          title: `${String(l.loan_type ?? '').replace(/_/g, ' ')} Loan`,
          sub: `Customer ${String(l.customer_id ?? '').slice(0, 8)}`,
          badge: 'Pending',
          badgeColor: 'text-amber-400 bg-amber-500/10',
          onClick: () => onNavigate('loans'),
        })));
      }).catch(() => setRecentItems([])).finally(() => setRecentLoading(false));
    } else {
      setRecentLabel('Recent Customers');
      customersApi.list({ limit: 5 }).then(r => {
        setRecentItems((r.customers ?? []).slice(0, 5).map((c: {id?: string; first_name?: string; last_name?: string; aml_risk_rating?: string; kyc_status?: string}) => ({
          id: String(c.id ?? ''),
          title: `${String(c.first_name ?? '')} ${String(c.last_name ?? '')}`,
          sub: `ID: ${String(c.id ?? '').slice(0, 8)}`,
          badge: String(c.aml_risk_rating ?? 'low'),
          badgeColor: c.aml_risk_rating === 'high' ? 'text-red-400 bg-red-500/10' : c.aml_risk_rating === 'medium' ? 'text-amber-400 bg-amber-500/10' : 'text-green-400 bg-green-500/10',
          onClick: () => onNavigate('customer_search'),
        })));
      }).catch(() => setRecentItems([])).finally(() => setRecentLoading(false));
    }
  }, [role, refreshKey]);

  const getHandler = (key: keyof KpiStats): (() => void) | undefined => {
    const action = KEY_ACTIONS[key];
    if (action === 'fraud') return onOpenFraud;
    if (action === 'customers') return onOpenCustomers;
    if (action === 'docs') return onOpenDocs;
    if (action === 'trust') return onOpenAITrust;
    if (action === 'nav') {
      const target = KEY_NAV_TARGET[key];
      if (target) return () => onNavigate(target);
    }
    return undefined;
  };

  return (
    <div className="h-full overflow-y-auto space-y-4 pr-1">
      {/* Hero header */}
      <GlassCard animate={false} className="px-6 py-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`w-12 h-12 rounded-2xl bg-gradient-to-br ${cfg.color} flex items-center justify-center text-2xl shadow-glow-sm`}>
              {cfg.icon}
            </div>
            <div>
              <h2 className="text-base font-bold text-t1">{cfg.title}</h2>
              <p className="text-xs text-t3 mt-0.5 max-w-md">{cfg.description}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-t3 bg-white/[0.04] border border-white/[0.08] px-2.5 py-1.5 rounded-lg">{roleLabel}</span>
            {(role === 'admin' || role === 'personal_banker' || role === 'branch_manager' || role === 'executive') && (
              <motion.button whileTap={{ scale: 0.97 }} onClick={onAddCustomer}
                className="text-xs px-3 py-1.5 rounded-lg bg-purple-500/15 border border-purple-500/25 text-purple-300 hover:bg-purple-500/25 transition-all">
                ➕ Add Customer
              </motion.button>
            )}
          </div>
        </div>
      </GlassCard>

      {/* KPI metrics */}
      <div className="grid grid-cols-4 gap-3">
        {cfg.kpis.map((kpi, i) => {
          const handler = getHandler(kpi.key);
          return (
            <motion.div key={kpi.key} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.07, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              onClick={handler}
              className={handler ? 'cursor-pointer group' : ''}>
              <GlassCard animate={false} className={`px-4 py-4 h-full transition-all duration-150${handler ? ' group-hover:border-purple-500/30 group-hover:bg-white/[0.05]' : ''}`}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xl">{kpi.icon}</span>
                  {handler && (
                    <span className="text-[8px] text-purple-400/50 border border-purple-500/15 px-1.5 py-0.5 rounded leading-tight opacity-0 group-hover:opacity-100 transition-opacity">
                      view all
                    </span>
                  )}
                </div>
                <div className={`text-2xl font-bold tabular-nums mb-1 ${kpi.color}`}>
                  {loading ? (
                    <span className="inline-block w-12 h-6 rounded bg-white/[0.06] animate-pulse" />
                  ) : kpiError ? (
                    <button onClick={loadKpi} className="text-xs text-red-400/70 hover:text-red-400 transition-colors">retry ↺</button>
                  ) : stats ? fmtVal(kpi.key, stats) : '—'}
                </div>
                <div className="text-[10px] text-t3 uppercase tracking-wider leading-tight">{kpi.label}</div>
                {handler && (
                  <div className="text-[9px] text-purple-400/60 mt-1.5">click to view →</div>
                )}
              </GlassCard>
            </motion.div>
          );
        })}
      </div>

      {/* Quick Links */}
      <GlassCard animate={false} className="px-5 py-4">
        <h3 className="text-[10px] text-t3 uppercase tracking-wider mb-3">Quick Actions</h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {cfg.quickLinks.map((link, i) => (
            <motion.button key={link.tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 + i * 0.06 }}
              whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }}
              onClick={() => onNavigate(link.tab)}
              className="flex flex-col items-start gap-1.5 p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]
                         hover:border-purple-500/25 hover:bg-purple-500/[0.06] transition-all text-left group">
              <span className="text-lg">{link.icon}</span>
              <div>
                <div className="text-xs font-medium text-t1 group-hover:text-purple-300 transition-colors">{link.label}</div>
                <div className="text-[9px] text-t3 leading-tight mt-0.5">{link.desc}</div>
              </div>
            </motion.button>
          ))}
        </div>
      </GlassCard>

      {/* Recent Activity */}
      <GlassCard animate={false} className="px-5 py-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-[10px] text-t3 uppercase tracking-wider">{recentLabel}</h3>
          <span className="text-[9px] text-purple-400/60">live from banking.db</span>
        </div>
        {recentLoading ? (
          <div className="flex items-center gap-2 py-3 text-xs text-t3">
            <div className="w-3 h-3 border border-purple-500 border-t-transparent rounded-full animate-spin" />
            Loading…
          </div>
        ) : recentItems.length === 0 ? (
          <p className="text-xs text-t3 py-2">No recent activity</p>
        ) : (
          <div className="space-y-1.5">
            {recentItems.map((item, i) => (
              <motion.button
                key={item.id + i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.5 + i * 0.05 }}
                whileHover={{ x: 2 }}
                onClick={item.onClick}
                className="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-white/[0.02] border border-white/[0.05] hover:border-purple-500/20 hover:bg-purple-500/[0.04] transition-all text-left group"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-t1 group-hover:text-purple-300 transition-colors capitalize truncate">{item.title}</div>
                  <div className="text-[9px] text-t3 font-mono mt-0.5">{item.sub}</div>
                </div>
                {item.badge && (
                  <span className={`text-[9px] font-medium px-2 py-0.5 rounded-full ml-3 flex-shrink-0 capitalize ${item.badgeColor}`}>
                    {item.badge.replace(/_/g, ' ')}
                  </span>
                )}
                <span className="text-t3/40 group-hover:text-purple-400/60 transition-colors ml-2 text-xs">→</span>
              </motion.button>
            ))}
          </div>
        )}
      </GlassCard>

      {/* Role-specific tip */}
      <GlassCard animate={false} className="px-5 py-3 border-l-2 border-purple-500/30">
        <div className="flex items-start gap-3">
          <span className="text-base mt-0.5">✦</span>
          <div>
            <div className="text-xs font-medium text-t1 mb-0.5">AI Copilot is role-aware</div>
            <p className="text-[10px] text-t3 leading-relaxed">
              The AI Copilot adapts its responses based on your role as <span className="text-purple-400">{roleLabel}</span>.
              Ask about policies, customer risk profiles, fraud patterns, or compliance obligations — the AI grounds every answer in TrustNova's 16 indexed policy documents.
            </p>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
