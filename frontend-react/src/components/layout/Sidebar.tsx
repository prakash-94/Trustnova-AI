import { motion } from 'framer-motion';
import clsx from 'clsx';
import { Auth } from '@/lib/auth';

interface NavItem {
  id: string;
  label: string;
  icon: string;
  section: string;
}

const NAV: NavItem[] = [
  { id: 'home',          label: 'Dashboard',        icon: '⊞', section: 'home' },
  { id: 'ai_copilot',   label: 'AI Copilot',       icon: '✦', section: 'ai_copilot' },
  { id: 'customer_search', label: 'Customer Search', icon: '⊙', section: 'customer_search' },
  { id: 'customer360',  label: 'Customer 360°',    icon: '◎', section: 'customer360' },
  { id: 'accounts',     label: 'Accounts',          icon: '⊟', section: 'accounts' },
  { id: 'transactions', label: 'Transactions',      icon: '⇄', section: 'transactions' },
  { id: 'loans',        label: 'Loans',             icon: '◈', section: 'loans' },
  { id: 'aml',          label: 'AML',               icon: '⚑', section: 'aml' },
  { id: 'kyc',          label: 'KYC',               icon: '✓', section: 'kyc' },
  { id: 'risk',         label: 'Risk',              icon: '◬', section: 'risk' },
  { id: 'fraud',        label: 'Fraud Monitor',     icon: '⚠', section: 'fraud' },
  { id: 'treasury',     label: 'Treasury',          icon: '◆', section: 'treasury' },
  { id: 'compliance',   label: 'Compliance',        icon: '⊕', section: 'compliance' },
  { id: 'appointments', label: 'Appointments',      icon: '◷', section: 'appointments' },
  { id: 'credit_cards', label: 'Credit Cards',      icon: '▣', section: 'credit_cards' },
  { id: 'admin',        label: 'Admin Center',      icon: '⚙', section: 'admin' },
];

interface Props {
  active: string;
  onNav: (id: string) => void;
  collapsed: boolean;
}

export default function Sidebar({ active, onNav, collapsed }: Props) {
  const user = Auth.getUser();
  const visible = NAV.filter(n => Auth.hasNavSection(n.section));

  return (
    <motion.aside
      animate={{ width: collapsed ? 64 : 220 }}
      transition={{ duration: 0.2 }}
      className="flex flex-col h-full overflow-hidden"
      style={{ background: 'rgba(7,7,15,0.95)', borderRight: '1px solid rgba(255,255,255,0.06)' }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 shadow-glow-sm"
          style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
          <span className="text-white text-sm font-bold">T</span>
        </div>
        {!collapsed && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
            <div className="gradient-text font-bold text-sm leading-tight">TrustNova</div>
            <div className="text-xs text-white/40">AI Banking</div>
          </motion.div>
        )}
      </div>

      {/* Nav items */}
      <nav className="flex-1 overflow-y-auto py-3 px-2">
        {visible.map(item => {
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNav(item.id)}
              title={collapsed ? item.label : undefined}
              className={clsx(
                'w-full flex items-center gap-3 px-3 py-2.5 rounded-xl mb-1 text-sm transition-all duration-150 text-left',
                isActive
                  ? 'bg-purple-600/20 text-purple-300 border border-purple-500/20'
                  : 'text-white/50 hover:text-white/80 hover:bg-white/5'
              )}
            >
              <span className="text-base flex-shrink-0">{item.icon}</span>
              {!collapsed && <span className="truncate">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* User badge */}
      {user && (
        <div className="px-3 py-3" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-semibold"
              style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
              {user.full_name?.[0] ?? 'U'}
            </div>
            {!collapsed && (
              <div className="min-w-0">
                <div className="text-xs text-white/80 truncate font-medium">{user.full_name}</div>
                <div className="text-xs text-white/40 truncate">{user.role_label ?? user.role}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </motion.aside>
  );
}
