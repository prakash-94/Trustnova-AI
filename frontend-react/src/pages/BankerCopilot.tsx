import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import AnimatedBackground from '@/components/background/AnimatedBackground';
import Sidebar from '@/components/layout/Sidebar';
import TopBar from '@/components/layout/TopBar';
import RoleDashboard from '@/components/dashboard/RoleDashboard';
import ChatInterface from '@/components/chat/ChatInterface';
import CustomerSearch from '@/components/customer/CustomerSearch';
import Customer360 from '@/components/customer/Customer360';
import AccountsCenter from '@/components/accounts/AccountsCenter';
import TransactionsCenter from '@/components/transactions/TransactionsCenter';
import BankLoansCenter from '@/components/loans/BankLoansCenter';
import AMLCenter from '@/components/aml/AMLCenter';
import KYCCenter from '@/components/kyc/KYCCenter';
import RiskCenter from '@/components/risk/RiskCenter';
import TreasuryDashboard from '@/components/treasury/TreasuryDashboard';
import ComplianceDashboard from '@/components/compliance/ComplianceDashboard';
import AccessRequestsPanel from '@/components/admin/AccessRequestsPanel';
import AppointmentsCenter from '@/components/appointments/AppointmentsCenter';
import CreditCardApplicationsCenter from '@/components/credit_cards/CreditCardApplicationsCenter';
import FraudMonitor from '@/pages/FraudMonitor';

interface Props { onLogout: () => void; }

export default function BankerCopilot({ onLogout }: Props) {
  const [active, setActive] = useState('home');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);

  const handleNav = (id: string) => {
    setActive(id);
    if (id !== 'customer360') setSelectedCustomerId(null);
  };

  const handleSelectCustomer = (id: string) => {
    setSelectedCustomerId(id);
    setActive('customer360');
  };

  const renderContent = () => {
    if (active === 'customer360' && selectedCustomerId) {
      return <Customer360 customerId={selectedCustomerId} onBack={() => handleNav('customer_search')} />;
    }
    switch (active) {
      case 'home':          return <RoleDashboard onNav={handleNav} />;
      case 'ai_copilot':   return <ChatInterface />;
      case 'customer_search': return <CustomerSearch onSelectCustomer={handleSelectCustomer} />;
      case 'accounts':     return <AccountsCenter />;
      case 'transactions': return <TransactionsCenter />;
      case 'loans':        return <BankLoansCenter />;
      case 'aml':          return <AMLCenter />;
      case 'kyc':          return <KYCCenter />;
      case 'risk':         return <RiskCenter />;
      case 'fraud':        return <FraudMonitor />;
      case 'treasury':     return <TreasuryDashboard />;
      case 'compliance':   return <ComplianceDashboard />;
      case 'admin':        return <AccessRequestsPanel />;
      case 'appointments': return <AppointmentsCenter />;
      case 'credit_cards': return <CreditCardApplicationsCenter />;
      default:             return <RoleDashboard onNav={handleNav} />;
    }
  };

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-primary)' }}>
      <AnimatedBackground />

      <div className="relative z-10 flex h-full w-full">
        <Sidebar active={active} onNav={handleNav} collapsed={sidebarCollapsed} />

        <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
          <TopBar
            onToggleSidebar={() => setSidebarCollapsed(c => !c)}
            onLogout={onLogout}
            onNav={handleNav}
          />

          <main className="flex-1 overflow-y-auto">
            <AnimatePresence mode="wait">
              <motion.div
                key={active + (selectedCustomerId ?? '')}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.15 }}
                className="min-h-full"
              >
                {renderContent()}
              </motion.div>
            </AnimatePresence>
          </main>
        </div>
      </div>
    </div>
  );
}
