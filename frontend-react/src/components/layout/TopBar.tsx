import { motion } from 'framer-motion';
import { Auth } from '@/services/auth';
import NotificationBell from '@/features/notifications/NotificationBell';
import type { NavSection } from './Sidebar';

const LABELS: Partial<Record<NavSection, string>> & Record<string, string> = {
  home:               'Dashboard',
  ai_copilot:         'AI Copilot',
  customer_search:    'Customer Search',
  customer360:        'Customer 360',
  accounts:           'Accounts',
  transactions:       'Transactions',
  loans:              'Loans & Credit',
  aml_center:         'AML Center',
  fraud_center:       'Fraud Center',
  kyc_center:         'KYC Center',
  risk_center:        'Risk Center',
  treasury_dashboard: 'Treasury Dashboard',
  compliance_center:  'Compliance',
  access_requests:    'Access Requests',
  admin_center:       'Admin Center',
  appointments:       'Appointments',
  credit_cards:       'Credit Card Applications',
};

const SUBTITLES: Partial<Record<NavSection, string>> & Record<string, string> = {
  home:               'Role-based overview and KPIs',
  ai_copilot:         'Llama 3.3 70B · Groq · RAG-powered',
  customer_search:    'Find and manage customer profiles',
  customer360:        'Comprehensive customer intelligence view',
  accounts:           'Account balances and management',
  transactions:       'Transaction history and monitoring',
  loans:              'Loan applications and portfolio',
  aml_center:         'Anti-Money Laundering monitoring',
  fraud_center:       'Fraud detection and investigation',
  kyc_center:         'Know Your Customer verification',
  risk_center:        'Credit and operational risk analytics',
  treasury_dashboard: 'Liquidity and cash position',
  compliance_center:  'Regulatory compliance and reporting',
  access_requests:    'Review and approve access requests',
  admin_center:       'Announcements · Feedback · User Management',
  appointments:       'Schedule and manage appointments with bank staff',
  credit_cards:       'Submit, track, and review credit card applications',
};

interface TopBarProps {
  activeTab: NavSection;
  onToggleSidebar?: () => void;
  onOpenFeedback?: () => void;
}

export default function TopBar({ activeTab, onToggleSidebar, onOpenFeedback }: TopBarProps) {
  const user = Auth.getUser();
  const now  = new Date();

  return (
    <header className="h-14 flex-shrink-0 glass border-b border-white/[0.05] flex items-center px-5 gap-4 z-10">
      {onToggleSidebar && (
        <button onClick={onToggleSidebar}
          className="text-t3 hover:text-t1 transition-colors text-lg leading-none flex-shrink-0">
          ☰
        </button>
      )}

      <motion.div
        key={activeTab}
        initial={{ opacity: 0, x: -8 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.2 }}
        className="flex-1 min-w-0"
      >
        <h1 className="text-sm font-semibold text-t1">{LABELS[activeTab] ?? activeTab}</h1>
        <p className="text-[11px] text-t3 truncate">{SUBTITLES[activeTab] ?? ''}</p>
      </motion.div>

      <div className="flex items-center gap-2">
        {/* Feedback button — visible to all users */}
        {onOpenFeedback && (
          <motion.button
            whileTap={{ scale: 0.93 }}
            onClick={onOpenFeedback}
            title="Submit feedback or bug report"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] text-t3 hover:text-t2 hover:bg-white/[0.05] border border-white/[0.05] hover:border-white/[0.10] transition-all font-medium"
          >
            <span>💬</span>
            <span className="hidden sm:block">Feedback</span>
          </motion.button>
        )}

        {/* Notification bell */}
        <NotificationBell />

        <div className="h-3 w-px bg-white/[0.08] mx-1" />

        <div className="hidden md:flex items-center gap-1.5 text-[11px] text-t3">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse-glow" />
          Systems operational
        </div>
        <div className="h-3 w-px bg-white/[0.08]" />
        <div className="text-[11px] text-t3 font-mono hidden sm:block">
          {now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {now.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
        </div>
        <div className="h-3 w-px bg-white/[0.08]" />
        <div className="text-[11px] px-2 py-1 rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-300 font-medium capitalize">
          {user?.role_label ?? user?.role?.replace(/_/g, ' ')}
        </div>
      </div>
    </header>
  );
}
