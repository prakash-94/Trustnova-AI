import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';
import { Auth } from '@/lib/auth';
import { accessRequestsApi } from '@/lib/api';

export type NavSection =
  | 'home' | 'ai_copilot' | 'customer_search' | 'customer360'
  | 'accounts' | 'transactions' | 'loans'
  | 'aml_center' | 'fraud_center' | 'kyc_center'
  | 'risk_center' | 'treasury_dashboard' | 'compliance_center'
  | 'access_requests' | 'admin_center'
  | 'appointments' | 'credit_cards';

/**
 * NAV_GROUPS — Sidebar navigation architecture.
 *
 * Two distinct workspaces (as per the architecture spec):
 *
 * A) CUSTOMER WORKSPACE — single customer view
 *    The "Customer" item combines search + 360 view.
 *    All inner tabs (Accounts, Transactions, Loans within Customer) appear
 *    INSIDE the Customer 360 component, not as separate sidebar items.
 *
 * B) BANK OPERATIONS WORKSPACE — bank-wide management
 *    Accounts     → ALL accounts across the institution (not one customer)
 *    Transactions → ALL transactions across the institution (bank-wide)
 *    Loans        → ALL loans across the institution (all types + statuses)
 *
 * IMPORTANT: These two groups must NEVER be confused:
 *   - Customer → customer-specific data for ONE selected customer
 *   - Accounts / Transactions / Loans → bank-wide operational modules
 */
const NAV_GROUPS = [
  {
    label: 'AI',
    items: [
      { id: 'home'       as NavSection, icon: '🏠',  label: 'Dashboard' },
      { id: 'ai_copilot' as NavSection, icon: '✦',  label: 'AI Copilot' },
    ],
  },
  {
    // Customer Workspace: Single-customer context
    // The Customer item shows search + Customer 360 (profile, overview, risk,
    // customer accounts, customer transactions, customer loans) in ONE page.
    label: 'Customer Workspace',
    items: [
      { id: 'customer_search' as NavSection, icon: '👤', label: 'Customer' },
      { id: 'appointments'    as NavSection, icon: '📅', label: 'Appointments' },
    ],
  },
  {
    // Bank Operations: Bank-wide management modules (NOT customer-specific)
    // These show aggregate data across ALL customers and accounts.
    label: 'Bank Operations',
    items: [
      { id: 'accounts'     as NavSection, icon: '🏦', label: 'Accounts' },
      { id: 'transactions' as NavSection, icon: '↔',  label: 'Transactions' },
      { id: 'loans'        as NavSection, icon: '📋', label: 'Loans' },
      { id: 'credit_cards' as NavSection, icon: '💳', label: 'Credit Cards' },
    ],
  },
  {
    label: 'Compliance',
    items: [
      { id: 'aml_center'   as NavSection, icon: '🔎', label: 'AML Center' },
      { id: 'kyc_center'   as NavSection, icon: '🪪', label: 'KYC Center' },
      { id: 'fraud_center' as NavSection, icon: '🛡', label: 'Fraud Center' },
      { id: 'risk_center'  as NavSection, icon: '📊', label: 'Risk Center' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { id: 'treasury_dashboard' as NavSection, icon: '💰', label: 'Treasury' },
      { id: 'compliance_center'  as NavSection, icon: '⚖',  label: 'Compliance' },
    ],
  },
];

/**
 * CUSTOMER_GATED: tabs that require a customer to be selected first.
 * NOTE: 'accounts', 'transactions', 'loans' are NO LONGER in this set
 * because they are now Bank Operations modules (bank-wide, no customer needed).
 * Only compliance/risk modules retain the customer-gating indicator.
 */
const CUSTOMER_GATED: Set<NavSection> = new Set([
  'aml_center', 'kyc_center', 'fraud_center', 'risk_center',
]);

interface SidebarProps {
  active: NavSection;
  onChange: (tab: NavSection) => void;
  onLogout: () => void;
  collapsed?: boolean;
  hasCustomer?: boolean;
  tempGrants?: Map<string, Date>;   // section id → expiry Date
  pendingAccessRequests?: number;   // live pending count shown on Access Requests item
}

// Countdown badge: shows "9m" or "45s" remaining for a temp grant
function GrantCountdown({ expiresAt }: { expiresAt: Date }) {
  const [remaining, setRemaining] = useState(
    Math.max(0, Math.round((expiresAt.getTime() - Date.now()) / 1000))
  );
  useEffect(() => {
    const t = setInterval(() => {
      setRemaining(Math.max(0, Math.round((expiresAt.getTime() - Date.now()) / 1000)));
    }, 1000);
    return () => clearInterval(t);
  }, [expiresAt]);

  if (remaining <= 0) return null;
  const label = remaining >= 60 ? `${Math.ceil(remaining / 60)}m` : `${remaining}s`;
  const urgent = remaining < 60;
  return (
    <span className={clsx(
      'ml-auto text-[9px] px-1.5 py-0.5 rounded border tabular-nums font-medium',
      urgent
        ? 'text-orange-300 border-orange-500/30 bg-orange-500/10'
        : 'text-green-300 border-green-500/30 bg-green-500/10',
    )}>
      ⏱ {label}
    </span>
  );
}

export default function Sidebar({ active, onChange, onLogout, collapsed, hasCustomer, tempGrants, pendingAccessRequests = 0 }: SidebarProps) {
  const user = Auth.getUser();
  const isAdmin = user?.role === 'admin';
  const [requesting, setRequesting] = useState<string | null>(null);
  const [requestedSections, setRequestedSections] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<string | null>(null);

  const handleRequestAccess = async (sectionId: string, sectionLabel: string) => {
    setRequesting(sectionId);
    try {
      await accessRequestsApi.submit(sectionId, `${user?.role_label ?? user?.role} requesting access to ${sectionLabel}`);
      setRequestedSections(prev => new Set([...prev, sectionId]));
      setToast(`Access request for "${sectionLabel}" sent to admin.`);
      setTimeout(() => setToast(null), 4000);
    } catch {
      setToast('Failed to submit request. Try again.');
      setTimeout(() => setToast(null), 3000);
    } finally {
      setRequesting(null);
    }
  };

  return (
    <aside className={clsx(
      'flex-shrink-0 glass border-r border-white/[0.05] flex flex-col z-10 transition-all duration-300',
      collapsed ? 'w-14' : 'w-56',
    )}>
      {/* Logo */}
      <div className="px-4 pt-5 pb-4 border-b border-white/[0.05]">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 flex-shrink-0 rounded-lg bg-gradient-to-br from-purple-500 to-blue-600 flex items-center justify-center text-sm shadow-glow-sm">
            ✦
          </div>
          {!collapsed && (
            <div>
              <div className="text-xs font-bold gradient-text leading-tight">TrustNova AI</div>
              <div className="text-[10px] text-t3">Banking Platform</div>
            </div>
          )}
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 space-y-4 px-2">
        {NAV_GROUPS.map(group => {
          // Items this role has by default
          const accessible = group.items.filter(item => Auth.hasNavSection(item.id));
          // Items that are normally locked but have an active temp grant
          const tempGranted = group.items.filter(
            item => !Auth.hasNavSection(item.id) && tempGrants?.has(item.id)
          );
          // Fully locked (no role access, no temp grant)
          const locked = group.items.filter(
            item => !Auth.hasNavSection(item.id) && !tempGrants?.has(item.id)
          );

          if (!accessible.length && !tempGranted.length && !locked.length) return null;
          return (
            <div key={group.label}>
              {!collapsed && (
                <div className="text-[10px] text-t3 uppercase tracking-widest font-medium px-2 mb-1.5">
                  {group.label}
                </div>
              )}
              <div className="space-y-0.5">
                {/* Accessible items (role-based) */}
                {accessible.map(item => {
                  const isActive = active === item.id;
                  const isGated = CUSTOMER_GATED.has(item.id) && !hasCustomer;
                  return (
                    <motion.button
                      key={item.id}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => onChange(item.id)}
                      title={collapsed ? item.label : isGated ? `${item.label} — select a customer first` : undefined}
                      className={clsx(
                        'w-full flex items-center gap-2.5 px-2 py-2 rounded-xl text-xs transition-all duration-150',
                        isActive
                          ? 'bg-purple-500/15 text-purple-300 border border-purple-500/20'
                          : isGated
                          ? 'text-t3/50 hover:text-t3 hover:bg-white/[0.02]'
                          : 'text-t3 hover:text-t1 hover:bg-white/[0.04]',
                      )}
                    >
                      <span className={clsx('text-sm w-4 text-center flex-shrink-0', isGated && !isActive && 'opacity-50')}>{item.icon}</span>
                      {!collapsed && <span className="font-medium truncate">{item.label}</span>}
                      {isActive && !collapsed && (
                        <motion.span layoutId="dot" className="ml-auto w-1.5 h-1.5 rounded-full bg-purple-400 flex-shrink-0" />
                      )}
                      {!isActive && isGated && !collapsed && (
                        <span className="ml-auto text-[8px] text-amber-400/50 flex-shrink-0">●</span>
                      )}
                    </motion.button>
                  );
                })}

                {/* Temp-granted items — accessible but with countdown timer */}
                {tempGranted.map(item => {
                  const isActive = active === item.id;
                  const expiresAt = tempGrants!.get(item.id)!;
                  return (
                    <motion.button
                      key={item.id}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => onChange(item.id)}
                      title={collapsed ? `${item.label} (temp access)` : undefined}
                      className={clsx(
                        'w-full flex items-center gap-2.5 px-2 py-2 rounded-xl text-xs transition-all duration-150',
                        isActive
                          ? 'bg-green-500/15 text-green-300 border border-green-500/20'
                          : 'text-green-400/70 hover:text-green-300 hover:bg-green-500/[0.06] border border-green-500/10',
                      )}
                    >
                      <span className="text-sm w-4 text-center flex-shrink-0">{item.icon}</span>
                      {!collapsed && <span className="font-medium truncate">{item.label}</span>}
                      {!collapsed && !isActive && <GrantCountdown expiresAt={expiresAt} />}
                      {isActive && !collapsed && (
                        <motion.span layoutId="dot" className="ml-auto w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />
                      )}
                    </motion.button>
                  );
                })}

                {/* Locked items with Request Access */}
                {!collapsed && locked.map(item => {
                  const alreadyRequested = requestedSections.has(item.id);
                  const isLoading = requesting === item.id;
                  return (
                    <div key={item.id}
                      className="w-full flex items-center gap-2 px-2 py-2 rounded-xl text-xs text-t3/40 group relative">
                      <span className="text-sm w-4 text-center flex-shrink-0 opacity-40">{item.icon}</span>
                      <span className="font-medium truncate flex-1">{item.label}</span>
                      <span className="text-[9px]">🔒</span>
                      {/* Request Access hover button */}
                      <div className="absolute inset-0 flex items-center justify-end pr-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => !alreadyRequested && handleRequestAccess(item.id, item.label)}
                          disabled={alreadyRequested || isLoading}
                          className={clsx(
                            'text-[9px] px-1.5 py-0.5 rounded border transition-all',
                            alreadyRequested
                              ? 'border-green-500/30 text-green-400/60 bg-green-500/10'
                              : 'border-purple-500/30 text-purple-300 bg-purple-500/10 hover:bg-purple-500/20',
                          )}
                        >
                          {isLoading ? '…' : alreadyRequested ? '✓ Requested' : 'Request Access'}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* Admin section */}
        {isAdmin && (
          <div>
            {!collapsed && (
              <div className="text-[10px] text-t3 uppercase tracking-widest font-medium px-2 mb-1.5">
                Admin
              </div>
            )}
            {[
              { id: 'access_requests' as NavSection, icon: '📥', label: 'Access Requests' },
              { id: 'admin_center'    as NavSection, icon: '🔑', label: 'Admin Center' },
            ].map(item => (
              <motion.button
                key={item.id}
                whileTap={{ scale: 0.97 }}
                onClick={() => onChange(item.id)}
                title={collapsed ? item.label : undefined}
                className={clsx(
                  'w-full flex items-center gap-2.5 px-2 py-2 rounded-xl text-xs transition-all duration-150 mb-0.5',
                  active === item.id
                    ? 'bg-amber-500/15 text-amber-300 border border-amber-500/20'
                    : 'text-t3 hover:text-t1 hover:bg-white/[0.04]',
                )}
              >
                <span className="text-sm w-4 text-center flex-shrink-0">{item.icon}</span>
                {!collapsed && <span className="font-medium">{item.label}</span>}
                {/* Pending badge — always visible while there are pending requests */}
                {!collapsed && item.id === 'access_requests' && pendingAccessRequests > 0 && (
                  <span className="ml-auto px-1.5 py-0.5 rounded-full bg-amber-500/20 border border-amber-500/30 text-amber-300 text-[9px] font-bold leading-none">
                    {pendingAccessRequests}
                  </span>
                )}
                {!collapsed && item.id !== 'access_requests' && active === item.id && (
                  <motion.span layoutId="adminDot" className="ml-auto w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                )}
              </motion.button>
            ))}
          </div>
        )}
      </nav>

      {/* Toast */}
      <AnimatePresence>
        {toast && !collapsed && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            className="mx-2 mb-2 px-3 py-2 rounded-xl bg-purple-500/15 border border-purple-500/20 text-[10px] text-purple-300"
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>

      {/* User */}
      <div className="border-t border-white/[0.05] px-3 py-3">
        {!collapsed && (
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-purple-500/30 to-blue-500/30 border border-purple-500/20 flex items-center justify-center text-xs font-bold text-purple-300 flex-shrink-0">
              {(user?.full_name?.[0] ?? user?.username?.[0] ?? 'U').toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-t1 truncate">{user?.full_name}</div>
              <div className="text-[10px] text-t3 capitalize truncate">{user?.role_label ?? user?.role?.replace(/_/g, ' ')}</div>
            </div>
          </div>
        )}
        <button
          onClick={onLogout}
          title={collapsed ? 'Sign out' : undefined}
          className="w-full text-xs text-t3 hover:text-red-400 transition-colors flex items-center gap-1.5 py-1"
        >
          <span className="text-sm">↩</span>
          {!collapsed && 'Sign out'}
        </button>
      </div>
    </aside>
  );
}
