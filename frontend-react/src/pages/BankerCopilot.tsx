import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { authApi, customersApi, accessRequestsApi } from '@/lib/api';
import type { Customer } from '@/types/banking';
import { Auth } from '@/lib/auth';
import type { User } from '@/types/banking';
import type { NavSection } from '@/components/layout/Sidebar';
import AnimatedBackground from '@/components/background/AnimatedBackground';
import Sidebar from '@/components/layout/Sidebar';
import TopBar from '@/components/layout/TopBar';
import GlassCard from '@/components/ui/GlassCard';

// Section components
import ChatInterface from '@/components/chat/ChatInterface';
import CustomerSearch from '@/components/customer/CustomerSearch';
import Customer360 from '@/components/customer/Customer360';
import AMLCenter from '@/components/aml/AMLCenter';
import KYCCenter from '@/components/kyc/KYCCenter';
import RiskCenter from '@/components/risk/RiskCenter';
import TreasuryDashboard from '@/components/treasury/TreasuryDashboard';
import ComplianceDashboard from '@/components/compliance/ComplianceDashboard';
import FraudMonitor from './FraudMonitor';
import AccessRequestsPanel from '@/components/admin/AccessRequestsPanel';
import RoleDashboard from '@/components/dashboard/RoleDashboard';

// Bank Operations Workspace
import AccountsCenter from '@/components/accounts/AccountsCenter';
import TransactionsCenter from '@/components/transactions/TransactionsCenter';
import BankLoansCenter from '@/components/loans/BankLoansCenter';

// Modals
import AddCustomerModal from '@/components/modals/AddCustomerModal';
import FraudAlertsModal from '@/components/modals/FraudAlertsModal';
import AITrustInfoModal from '@/components/modals/AITrustInfoModal';
import FeedbackBugModal from '@/components/modals/FeedbackBugModal';
import DocumentsModal from '@/components/modals/DocumentsModal';

// Admin
import AdminCenter from '@/pages/admin/AdminCenter';

// Executive & Banker features
import AppointmentsCenter from '@/components/appointments/AppointmentsCenter';
import CreditCardApplicationsCenter from '@/components/credit_cards/CreditCardApplicationsCenter';

import type { CustomerSummary } from '@/types';
import ChatHistorySidebar from '@/components/chat/ChatHistorySidebar';
import {
  type Conversation,
  loadConversations,
  saveConversations,
  makeConversation,
  getTitleFromMessages,
} from '@/lib/conversations';
import type { ChatMessage } from '@/types/banking';

/**
 * CUSTOMER_GATED_TABS — tabs that require a customer to be selected.
 * Compliance/investigation centers are NOT gated — they show bank-wide data
 * by default and only filter by customer when one is selected in banker roles.
 */
const CUSTOMER_GATED_TABS = new Set<NavSection>([]);

// Roles that view compliance centers bank-wide (no customer context filter)
// Must match the role keys from the backend ROLES dict (lowercase_underscore)
const BANK_WIDE_ROLES = new Set([
  'admin', 'fraud_analyst', 'aml_analyst', 'kyc_analyst',
  'credit_risk_analyst', 'treasury_analyst', 'executive',
]);

interface BankerCopilotProps {
  user: User;
  onLogout: () => void;
}

function NeedsCustomer({ tabLabel, onGoSearch }: { tabLabel: string; onGoSearch: () => void }) {
  return (
    <GlassCard animate={false} className="flex flex-col items-center justify-center py-24 text-center">
      <div className="text-4xl mb-4">🔍</div>
      <h3 className="text-base font-semibold text-t1 mb-2">Select a Customer First</h3>
      <p className="text-sm text-t3 mb-5 max-w-xs">
        {tabLabel} requires a customer context. Search for a customer to activate this view.
      </p>
      <motion.button whileTap={{ scale: 0.96 }} onClick={onGoSearch}
        className="px-4 py-2 rounded-xl bg-purple-500/15 border border-purple-500/25 text-sm text-purple-300 hover:bg-purple-500/25 transition-all">
        Go to Customer Search →
      </motion.button>
    </GlassCard>
  );
}

// Map from section id → expiry Date for temporary access grants
// Date is constructed from the server's UTC expires_at string (ends in Z)
type TempGrants = Map<string, Date>;

export default function BankerCopilot({ user, onLogout }: BankerCopilotProps) {
  const [activeTab, setActiveTab] = useState<NavSection>('home');
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerSummary | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [tempGrants, setTempGrants] = useState<TempGrants>(new Map());
  const [grantToast, setGrantToast] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [showCustomersModal, setShowCustomersModal] = useState(false);
  const [showDocsModal, setShowDocsModal] = useState(false);
  const [showFraudModal, setShowFraudModal] = useState(false);
  const [showAddCustomer, setShowAddCustomer] = useState(false);
  const [showAITrustInfo, setShowAITrustInfo] = useState(false);
  const [addToast, setAddToast] = useState<string | null>(null);
  const [customersList, setCustomersList] = useState<Customer[]>([]);
  const [customersLoading, setCustomersLoading] = useState(false);
  const [customersSearch, setCustomersSearch] = useState('');

  const [kpiRefreshKey, setKpiRefreshKey] = useState(0);
  const [showFeedback, setShowFeedback] = useState(false);

  // ── Conversation history ──────────────────────────────────────────────────
  const initConvState = useMemo(() => {
    const loaded = loadConversations();
    if (loaded.length > 0) {
      const sorted = [...loaded].sort((a, b) => b.updatedAt - a.updatedAt);
      return { convs: sorted, activeId: sorted[0].id };
    }
    const first = makeConversation([]);
    saveConversations([first]);
    return { convs: [first], activeId: first.id };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [conversations, setConversations] = useState<Conversation[]>(initConvState.convs);
  const [activeConvId, setActiveConvId]   = useState<string>(initConvState.activeId);

  const handleConvUpdate = useCallback((messages: ChatMessage[]) => {
    setConversations(prev => {
      const updated = prev.map(c => {
        if (c.id !== activeConvId) return c;
        const title = getTitleFromMessages(messages);
        return { ...c, messages, title: title || c.title, updatedAt: Date.now() };
      });
      saveConversations(updated);
      return updated;
    });
  }, [activeConvId]);

  const handleNewConv = useCallback(() => {
    const newConv = makeConversation([]);
    setConversations(prev => {
      const updated = [newConv, ...prev];
      saveConversations(updated);
      return updated;
    });
    setActiveConvId(newConv.id);
  }, []);

  const handleSelectConv = useCallback((id: string) => {
    setActiveConvId(id);
  }, []);

  const handleDeleteConv = useCallback((id: string) => {
    setConversations(prev => {
      const updated = prev.filter(c => c.id !== id);
      if (updated.length === 0) {
        const fresh = makeConversation([]);
        saveConversations([fresh]);
        setActiveConvId(fresh.id);
        return [fresh];
      }
      saveConversations(updated);
      if (id === activeConvId) {
        setActiveConvId(updated[0].id);
      }
      return updated;
    });
  }, [activeConvId]);

  // Load customers when modal opens
  useEffect(() => {
    if (!showCustomersModal) return;
    setCustomersLoading(true);
    customersApi.list({ limit: 200 })
      .then(r => setCustomersList(r.customers ?? []))
      .catch(() => setCustomersList([]))
      .finally(() => setCustomersLoading(false));
  }, [showCustomersModal]);

  // Poll for temporary access grants every 30 seconds.
  // When admin approves a request the section unlocks automatically in the sidebar.
  const fetchGrants = useCallback(() => {
    accessRequestsApi.myGrants().then(res => {
      const next = new Map<string, Date>();
      for (const g of res.grants) {
        next.set(g.section, new Date(g.expires_at));
      }
      setTempGrants(prev => {
        // Detect newly approved grants and show a toast
        for (const [section] of next) {
          if (!prev.has(section)) {
            const label = section.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            setGrantToast(`Access granted: ${label}`);
            setTimeout(() => setGrantToast(null), 6000);
          }
        }
        return next;
      });
    }).catch(() => { /* ignore — user may not have any grants */ });
  }, []);

  useEffect(() => {
    fetchGrants();
    pollRef.current = setInterval(fetchGrants, 30_000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchGrants]);

  // Listen for navigation events dispatched by NotificationBell popup
  useEffect(() => {
    const handler = (e: Event) => {
      const section = (e as CustomEvent<{ section: NavSection }>).detail?.section;
      if (section) setActiveTab(section);
    };
    window.addEventListener('tn:navigate', handler);
    return () => window.removeEventListener('tn:navigate', handler);
  }, []);

  const handleLogout = async () => {
    try { await authApi.logout(); } catch { /* ignore */ }
    Auth.clear();
    onLogout();
  };

  const handleSelectCustomer = (c: CustomerSummary) => {
    setSelectedCustomer(c);
  };

  const handleClearCustomer = () => {
    setSelectedCustomer(null);
  };

  const tabLabel = (tab: NavSection) => tab.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  const gatedContent = (tab: NavSection, content: React.ReactNode) => {
    if (!CUSTOMER_GATED_TABS.has(tab)) return content;
    if (!selectedCustomer) {
      return <NeedsCustomer tabLabel={tabLabel(tab)} onGoSearch={() => setActiveTab('customer_search')} />;
    }
    return content;
  };

  const renderSection = () => {
    switch (activeTab) {
      case 'ai_copilot': {
        const activeConv = conversations.find(c => c.id === activeConvId);
        return (
          <motion.div key="ai_copilot" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }} className="h-full flex gap-1.5">
            <ChatHistorySidebar
              conversations={conversations}
              activeId={activeConvId}
              onSelect={handleSelectConv}
              onNew={handleNewConv}
              onDelete={handleDeleteConv}
            />
            <div className="flex-1 min-w-0 h-full">
              <ChatInterface
                key={activeConvId}
                initialMessages={activeConv?.messages ?? []}
                onMessagesUpdate={handleConvUpdate}
                onClear={handleNewConv}
                customer={selectedCustomer}
                onShowDocs={() => setShowDocsModal(true)}
                onOpenFraud={() => setShowFraudModal(true)}
                role={user.role}
              />
            </div>
          </motion.div>
        );
      }

      case 'customer_search':
        return (
          <motion.div key="customer_search" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
            className="space-y-4">
            {/* Search / selector always visible at top */}
            <GlassCard animate={false} className="p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-t1">Customer</h2>
                {selectedCustomer && (
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-t3 uppercase tracking-wide">Selected:</span>
                    <span className="text-xs text-purple-300 font-medium">{selectedCustomer.name}</span>
                    <button onClick={handleClearCustomer}
                      className="text-[10px] text-t3 hover:text-red-400 transition-colors px-1.5 py-0.5 rounded border border-white/[0.06] hover:border-red-500/20">
                      ✕ change
                    </button>
                  </div>
                )}
              </div>
              {!selectedCustomer && (
                <CustomerSearch onSelect={c => { handleSelectCustomer(c); }} />
              )}
            </GlassCard>

            {/* Customer 360 view loads directly below once a customer is selected */}
            {selectedCustomer && (
              <Customer360 customer={selectedCustomer} onClearCustomer={handleClearCustomer} />
            )}
          </motion.div>
        );

      case 'customer360':
        // Falls through to customer_search — always renders the unified Customer view
        return (
          <motion.div key="customer_search" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
            className="space-y-4">
            <GlassCard animate={false} className="p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-t1">Customer</h2>
                {selectedCustomer && (
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-t3 uppercase tracking-wide">Selected:</span>
                    <span className="text-xs text-purple-300 font-medium">{selectedCustomer.name}</span>
                    <button onClick={handleClearCustomer}
                      className="text-[10px] text-t3 hover:text-red-400 transition-colors px-1.5 py-0.5 rounded border border-white/[0.06] hover:border-red-500/20">
                      ✕ change
                    </button>
                  </div>
                )}
              </div>
              {!selectedCustomer && <CustomerSearch onSelect={handleSelectCustomer} />}
            </GlassCard>
            {selectedCustomer && <Customer360 customer={selectedCustomer} onClearCustomer={handleClearCustomer} />}
          </motion.div>
        );

      /**
       * BANK OPERATIONS: Accounts
       * Shows ALL accounts across the institution — not a single customer's accounts.
       * The customer-specific accounts view lives inside Customer 360 → Accounts tab.
       *
       * Input:  none (no customer required)
       * Output: AccountsCenter with 7 tabs (Personal, Student, Business, etc.)
       */
      case 'accounts':
        return (
          <motion.div key="accounts" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <AccountsCenter onSelectCustomer={c => { handleSelectCustomer(c); setActiveTab('customer_search'); }} />
          </motion.div>
        );

      /**
       * BANK OPERATIONS: Transactions
       * Shows ALL bank transactions grouped by time period.
       * The customer-specific transactions view lives inside Customer 360 → Transactions tab.
       *
       * Input:  none (no customer required)
       * Output: TransactionsCenter with 6 period tabs (Daily → Annual)
       */
      case 'transactions':
        return (
          <motion.div key="transactions" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <TransactionsCenter />
          </motion.div>
        );

      /**
       * BANK OPERATIONS: Loans
       * Shows ALL loans across the institution by loan type and status.
       * The customer-specific loans view lives inside Customer 360 → Loans tab.
       *
       * Input:  none (no customer required)
       * Output: BankLoansCenter with type tabs + status filter pills
       */
      case 'loans':
        return (
          <motion.div key="loans" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <BankLoansCenter />
          </motion.div>
        );

      case 'aml_center':
        return (
          <motion.div key="aml_center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <AMLCenter customer={BANK_WIDE_ROLES.has(user.role) ? null : selectedCustomer} />
          </motion.div>
        );

      case 'fraud_center':
        return (
          <motion.div key="fraud_center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <FraudMonitor customer={BANK_WIDE_ROLES.has(user.role) ? null : selectedCustomer} />
          </motion.div>
        );

      case 'kyc_center':
        return (
          <motion.div key="kyc_center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <KYCCenter customer={BANK_WIDE_ROLES.has(user.role) ? null : selectedCustomer} />
          </motion.div>
        );

      case 'risk_center':
        return (
          <motion.div key="risk_center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            {gatedContent('risk_center', <RiskCenter customer={selectedCustomer} />)}
          </motion.div>
        );

      case 'treasury_dashboard':
        return (
          <motion.div key="treasury_dashboard" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <GlassCard animate={false} className="px-5 py-4 mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-t1">Treasury Dashboard</h2>
                <p className="text-xs text-t3">Liquidity, cash flows, reserve position, and Basel III regulatory ratios</p>
              </div>
            </GlassCard>
            <TreasuryDashboard />
          </motion.div>
        );

      case 'compliance_center':
        return (
          <motion.div key="compliance_center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <GlassCard animate={false} className="px-5 py-4 mb-4">
              <h2 className="text-sm font-semibold text-t1">Compliance Dashboard</h2>
              <p className="text-xs text-t3">Regulatory controls, complaints log, audit schedule</p>
            </GlassCard>
            <ComplianceDashboard />
          </motion.div>
        );

      case 'home':
        return (
          <motion.div key="home" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }} className="h-full">
            <RoleDashboard
              role={user.role}
              roleLabel={user.role_label ?? user.role.replace(/_/g, ' ')}
              onNavigate={setActiveTab}
              onAddCustomer={() => setShowAddCustomer(true)}
              onOpenFraud={() => setShowFraudModal(true)}
              onOpenCustomers={() => setShowCustomersModal(true)}
              onOpenDocs={() => setShowDocsModal(true)}
              onOpenAITrust={() => setShowAITrustInfo(true)}
              refreshKey={kpiRefreshKey}
            />
          </motion.div>
        );

      case 'access_requests':
        return (
          <motion.div key="access_requests" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <AccessRequestsPanel />
          </motion.div>
        );

      case 'admin_center':
        return (
          <motion.div key="admin_center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <AdminCenter />
          </motion.div>
        );

      case 'appointments':
        return (
          <motion.div key="appointments" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <AppointmentsCenter />
          </motion.div>
        );

      case 'credit_cards':
        return (
          <motion.div key="credit_cards" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <CreditCardApplicationsCenter />
          </motion.div>
        );

      default:
        return (
          <GlassCard animate={false} className="flex flex-col items-center justify-center py-24 text-center">
            <div className="text-4xl mb-4">🚧</div>
            <h3 className="text-lg font-semibold text-t1 mb-1">{tabLabel(activeTab)}</h3>
            <p className="text-sm text-t3">Coming soon in the next release</p>
          </GlassCard>
        );
    }
  };

  return (
    <div className="h-full flex relative overflow-hidden">
      <AnimatedBackground />

      <Sidebar
        active={activeTab}
        onChange={setActiveTab}
        onLogout={handleLogout}
        collapsed={collapsed}
        hasCustomer={!!selectedCustomer}
        tempGrants={tempGrants}
      />

      {/* Grant notification toast */}
      <AnimatePresence>
        {grantToast && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2.5 rounded-xl bg-green-500/20 border border-green-500/30 text-sm text-green-300 font-medium shadow-xl backdrop-blur-sm"
          >
            ✓ {grantToast}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex-1 flex flex-col min-w-0 z-10">
        <TopBar
          activeTab={activeTab}
          onToggleSidebar={() => setCollapsed(v => !v)}
          onOpenFeedback={() => setShowFeedback(true)}
        />

        <main className={`flex-1 flex flex-col overflow-hidden min-h-0 ${activeTab === 'ai_copilot' ? 'p-1.5 gap-1.5' : 'p-5 gap-4'}`}>
          <div className="flex-1 min-h-0 overflow-y-auto">
            <AnimatePresence mode="wait">
              {renderSection()}
            </AnimatePresence>
          </div>
        </main>
      </div>

      {/* ── Active Customers Modal ─────────────────────────────────────────── */}
      <AnimatePresence>
        {showCustomersModal && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            onClick={e => { if (e.target === e.currentTarget) setShowCustomersModal(false); }}>
            <motion.div initial={{ scale: 0.94, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.94, opacity: 0 }} transition={{ duration: 0.2 }}
              className="glass-card w-full max-w-3xl max-h-[80vh] flex flex-col overflow-hidden">
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
                <div>
                  <h2 className="text-base font-semibold text-t1">👥 Active Customers</h2>
                  <p className="text-xs text-t3 mt-0.5">{customersList.length} customers in database</p>
                </div>
                <button onClick={() => setShowCustomersModal(false)}
                  className="text-t3 hover:text-t1 text-xl leading-none w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white/[0.06] transition-all">✕</button>
              </div>
              {/* Search */}
              <div className="px-6 py-3 border-b border-white/[0.04]">
                <input
                  type="text"
                  value={customersSearch}
                  onChange={e => setCustomersSearch(e.target.value)}
                  placeholder="Search by first name or last name…"
                  className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-2.5 text-sm text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 transition-colors"
                />
              </div>
              {/* List */}
              <div className="flex-1 overflow-y-auto px-6 py-3">
                {customersLoading ? (
                  <div className="flex items-center justify-center py-16 text-t3 text-sm">Loading customers…</div>
                ) : (() => {
                  const q = customersSearch.toLowerCase().trim();
                  const filtered = q
                    ? customersList.filter(c =>
                        c.first_name.toLowerCase().includes(q) ||
                        c.last_name.toLowerCase().includes(q) ||
                        `${c.first_name} ${c.last_name}`.toLowerCase().includes(q)
                      )
                    : customersList;
                  if (!filtered.length) return (
                    <div className="text-center py-16 text-t3 text-sm">No customers match "{customersSearch}".</div>
                  );
                  const selectCustomer = (c: Customer) => {
                    handleSelectCustomer({ customer_id: c.id, name: `${c.first_name} ${c.last_name}`, email: c.email });
                    setShowCustomersModal(false);
                    setActiveTab('customer_search');
                  };
                  return (
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-t3 uppercase tracking-wider border-b border-white/[0.06]">
                          <th className="text-left pb-2 pr-4 font-medium">Full Name</th>
                          <th className="text-left pb-2 pr-4 font-medium">ID</th>
                          <th className="text-left pb-2 pr-4 font-medium">Segment</th>
                          <th className="text-left pb-2 pr-4 font-medium">KYC</th>
                          <th className="text-left pb-2 pr-4 font-medium">Credit</th>
                          <th className="text-left pb-2 font-medium">Risk</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map(c => (
                          <tr key={c.id}
                            onClick={() => selectCustomer(c)}
                            className="border-b border-white/[0.03] hover:bg-purple-500/[0.08] hover:border-purple-500/20 cursor-pointer transition-colors group">
                            <td className="py-2.5 pr-4">
                              <div className="font-semibold text-t1 group-hover:text-purple-300 transition-colors">
                                {c.first_name} {c.last_name}
                              </div>
                              <div className="text-[10px] text-purple-400/60 mt-0.5">Click to open profile →</div>
                            </td>
                            <td className="py-2.5 pr-4 text-purple-400 font-mono">{c.id}</td>
                            <td className="py-2.5 pr-4 text-t2 capitalize">{c.segment ?? '—'}</td>
                            <td className="py-2.5 pr-4">
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                                c.kyc_status === 'verified' ? 'bg-green-500/10 text-green-400' :
                                c.kyc_status === 'pending'  ? 'bg-amber-500/10 text-amber-400' :
                                'bg-red-500/10 text-red-400'
                              }`}>{c.kyc_status ?? '—'}</span>
                            </td>
                            <td className="py-2.5 pr-4 text-t2 tabular-nums">{c.credit_score ?? '—'}</td>
                            <td className="py-2.5">
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                                c.aml_risk_rating === 'high'   ? 'bg-red-500/10 text-red-400' :
                                c.aml_risk_rating === 'medium' ? 'bg-amber-500/10 text-amber-400' :
                                'bg-green-500/10 text-green-400'
                              }`}>{c.aml_risk_rating ?? 'low'}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  );
                })()}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Fraud Alerts Modal ──────────────────────────────────────────────── */}
      <AnimatePresence>
        {showFraudModal && (
          <FraudAlertsModal onClose={() => setShowFraudModal(false)} />
        )}
      </AnimatePresence>

      {/* ── Add Customer Modal ───────────────────────────────────────────────── */}
      <AnimatePresence>
        {showAddCustomer && (
          <AddCustomerModal
            onClose={() => setShowAddCustomer(false)}
            onCreated={(name, customerId) => {
              setShowAddCustomer(false);
              setKpiRefreshKey(k => k + 1);
              // Navigate directly to the new customer's profile
              handleSelectCustomer({ customer_id: customerId, name });
              setActiveTab('customer_search');
              setAddToast(`Customer ${name} created · opening profile…`);
              setTimeout(() => setAddToast(null), 4000);
            }}
          />
        )}
      </AnimatePresence>

      {/* ── AI Trust Info Modal ──────────────────────────────────────────────── */}
      <AnimatePresence>
        {showAITrustInfo && (
          <AITrustInfoModal onClose={() => setShowAITrustInfo(false)} />
        )}
      </AnimatePresence>

      {/* ── Feedback / Bug Report Modal ─────────────────────────────────────── */}
      <AnimatePresence>
        {showFeedback && (
          <FeedbackBugModal onClose={() => setShowFeedback(false)} />
        )}
      </AnimatePresence>

      {/* ── Add Customer Success Toast ───────────────────────────────────────── */}
      <AnimatePresence>
        {addToast && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-5 py-3 rounded-xl bg-green-500/20 border border-green-500/30 text-sm text-green-300 font-medium shadow-xl backdrop-blur-sm whitespace-nowrap"
          >
            ✓ {addToast}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Documents Modal ──────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showDocsModal && <DocumentsModal onClose={() => setShowDocsModal(false)} />}
      </AnimatePresence>
    </div>
  );
}
