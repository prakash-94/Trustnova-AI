import { useState, useRef, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { chatApi, kpiApi, type ChatResult, type KpiStats } from '@/services/api';
import { Auth } from '@/services/auth';
import GlassCard from '@/components/common/GlassCard';
import AIStatusBadge from './AIStatusBadge';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import type { ChatMessage, AgentId } from '@/types/banking';
import type { CustomerSummary } from '@/types';

let msgIdCounter = Date.now(); // start high to avoid collisions across mounts
const nextId = () => String(++msgIdCounter);

type QuickAction = { label: string; prompt: string; agent: AgentId; icon: string };

const ROLE_PERSONA: Record<string, { name: string; description: string; gradient: string; icon: string }> = {
  admin:               { name: 'Admin Copilot',        description: 'Full platform intelligence & oversight',         gradient: 'from-purple-500 to-blue-600',   icon: '⚙' },
  personal_banker:     { name: 'Banker Copilot',        description: 'Customer relationship & onboarding AI',         gradient: 'from-blue-500 to-cyan-500',     icon: '👤' },
  branch_manager:      { name: 'Manager Copilot',       description: 'Branch operations & team oversight AI',         gradient: 'from-indigo-500 to-violet-600', icon: '🏦' },
  loan_officer:        { name: 'Loan Copilot',          description: 'Loan analysis & approval decisioning AI',       gradient: 'from-green-500 to-teal-500',    icon: '📋' },
  mortgage_officer:    { name: 'Mortgage Copilot',      description: 'Mortgage & property risk analysis AI',          gradient: 'from-teal-500 to-cyan-600',     icon: '🏠' },
  underwriter:         { name: 'Underwriter Copilot',   description: 'Credit underwriting & risk decisioning AI',     gradient: 'from-amber-500 to-orange-500',  icon: '📊' },
  aml_analyst:         { name: 'AML Copilot',           description: 'Anti-money laundering & SAR intelligence',      gradient: 'from-red-600 to-rose-500',      icon: '🔎' },
  kyc_analyst:         { name: 'KYC Copilot',           description: 'Know Your Customer & identity verification AI', gradient: 'from-violet-500 to-purple-600', icon: '🪪' },
  fraud_analyst:       { name: 'Fraud Copilot',         description: 'Fraud detection & investigation AI',            gradient: 'from-orange-500 to-red-500',    icon: '🛡' },
  commercial_banker:   { name: 'Commercial Copilot',    description: 'Commercial banking relationship AI',            gradient: 'from-cyan-500 to-blue-500',     icon: '🏢' },
  credit_risk_analyst: { name: 'Credit Risk Copilot',   description: 'Credit risk scoring & portfolio analysis AI',   gradient: 'from-yellow-500 to-amber-500',  icon: '⚠' },
  operations_specialist:{ name: 'Operations Copilot',  description: 'Wire transfers & operations intelligence AI',    gradient: 'from-slate-400 to-slate-600',   icon: '⚙' },
  treasury_analyst:    { name: 'Treasury Copilot',      description: 'Liquidity & treasury management AI',            gradient: 'from-emerald-500 to-green-500', icon: '💰' },
  executive:           { name: 'Executive Copilot',     description: 'Strategic insights & portfolio overview AI',    gradient: 'from-purple-600 to-pink-500',   icon: '✦' },
};

const ROLE_QUICK_ACTIONS: Record<string, QuickAction[]> = {
  admin: [
    { label: 'Platform Overview',  prompt: 'Give me a full platform overview — fraud alerts, KYC, loans, and AML status.',         agent: 'executive_insights', icon: '✦' },
    { label: 'Fraud Alerts',       prompt: 'What are the active fraud alerts and critical cases?',                                  agent: 'fraud_detection',    icon: '🛡' },
    { label: 'AML Status',         prompt: 'Summarize open AML cases and any pending SAR filing requirements.',                    agent: 'aml_agent',          icon: '🔎' },
    { label: 'KYC Queue',          prompt: 'Which customers have pending KYC and what documents are missing?',                    agent: 'kyc_agent',          icon: '🪪' },
    { label: 'Loan Pipeline',      prompt: 'What is the current loan pipeline status and pending approvals?',                     agent: 'loan_decision',      icon: '📋' },
    { label: 'Compliance Check',   prompt: 'What compliance obligations are due this month?',                                     agent: 'compliance_agent',   icon: '⚖' },
  ],
  personal_banker: [
    { label: 'Customer Summary',   prompt: 'Give me a 360 summary for this customer including trust score and recent activity.',   agent: 'customer_360',       icon: '👤' },
    { label: 'KYC Pending',        prompt: 'Which customers have pending KYC verification and what documents are missing?',       agent: 'kyc_agent',          icon: '🪪' },
    { label: 'Product Recs',       prompt: 'What product recommendations are suitable for this customer based on their profile?', agent: 'customer_360',       icon: '💡' },
    { label: 'Trust Score',        prompt: 'Explain the trust score breakdown and what drives it for this customer.',             agent: 'customer_360',       icon: '✦' },
    { label: 'Account Review',     prompt: 'Review recent account activity and flag anything unusual.',                          agent: 'fraud_detection',    icon: '🔍' },
    { label: 'Onboarding Steps',   prompt: 'What are the required onboarding steps and compliance checks for new customers?',    agent: 'kyc_agent',          icon: '📋' },
  ],
  branch_manager: [
    { label: 'Branch Overview',    prompt: 'Give me a branch operations overview — customers, loans, fraud, and compliance.',     agent: 'executive_insights', icon: '🏦' },
    { label: 'Fraud Alerts',       prompt: 'What active fraud alerts require immediate branch attention?',                        agent: 'fraud_detection',    icon: '🛡' },
    { label: 'Loan Pipeline',      prompt: 'Summarize the current loan pipeline and pending approvals in the branch.',           agent: 'loan_decision',      icon: '📋' },
    { label: 'Team KYC Queue',     prompt: 'How many customers have pending KYC and what is the average completion time?',       agent: 'kyc_agent',          icon: '🪪' },
    { label: 'Customer Risk',      prompt: 'Who are the highest-risk customers and what actions are recommended?',               agent: 'risk_analysis',      icon: '⚠' },
    { label: 'Compliance Due',     prompt: 'What compliance reporting obligations are due this quarter?',                        agent: 'compliance_agent',   icon: '⚖' },
  ],
  loan_officer: [
    { label: 'Loan Eligibility',   prompt: 'What are the current loan approval criteria, DTI thresholds, and LTV limits?',       agent: 'loan_decision',      icon: '📋' },
    { label: 'Credit Analysis',    prompt: 'Perform a credit analysis for this customer — score, history, and DTI.',             agent: 'loan_decision',      icon: '💳' },
    { label: 'Risk Assessment',    prompt: 'What is the credit risk rating and key risk factors for this loan application?',     agent: 'risk_analysis',      icon: '📊' },
    { label: 'DTI Calculator',     prompt: 'Calculate the debt-to-income ratio and assess loan serviceability.',                 agent: 'loan_decision',      icon: '🔢' },
    { label: 'Pending Reviews',    prompt: 'What loan applications are pending review and what information is still needed?',    agent: 'loan_decision',      icon: '⏳' },
    { label: 'Policy Limits',      prompt: 'What are the lending policy limits and regulatory requirements for our loan products?', agent: 'policy_agent',    icon: '📜' },
  ],
  mortgage_officer: [
    { label: 'Mortgage Analysis',  prompt: 'Analyze this mortgage application — LTV, DTI, property risk, and approval outlook.', agent: 'loan_decision',      icon: '🏠' },
    { label: 'LTV Assessment',     prompt: 'What is the loan-to-value ratio and how does it affect approval?',                   agent: 'loan_decision',      icon: '📊' },
    { label: 'Underwriting Criteria', prompt: 'What are the underwriting criteria and risk thresholds for mortgage approvals?',  agent: 'loan_decision',      icon: '📋' },
    { label: 'Customer Financials', prompt: 'Review this customer\'s financial position for mortgage qualification.',            agent: 'customer_360',       icon: '💰' },
    { label: 'Rate & Terms',       prompt: 'What are the current mortgage rate options and term structures available?',          agent: 'policy_agent',       icon: '📈' },
    { label: 'Compliance Check',   prompt: 'What RESPA and TILA disclosures are required for this mortgage product?',           agent: 'compliance_agent',   icon: '⚖' },
  ],
  underwriter: [
    { label: 'Credit Underwriting', prompt: 'Perform a full credit underwriting review for this applicant.',                    agent: 'risk_analysis',      icon: '📊' },
    { label: 'Risk Decision',      prompt: 'What is the risk-based pricing recommendation and approval decision?',              agent: 'risk_analysis',      icon: '⚠' },
    { label: 'DTI & LTV',          prompt: 'Calculate DTI, LTV, and assess against underwriting thresholds.',                   agent: 'loan_decision',      icon: '🔢' },
    { label: 'Collateral Review',  prompt: 'Review collateral quality and adequacy for this loan application.',                 agent: 'loan_decision',      icon: '🏛' },
    { label: 'Exception Request',  prompt: 'What are the policy guidelines for underwriting exceptions?',                       agent: 'policy_agent',       icon: '📋' },
    { label: 'Regulatory Limits',  prompt: 'What regulatory capital and concentration limits apply to this loan type?',         agent: 'compliance_agent',   icon: '⚖' },
  ],
  aml_analyst: [
    { label: 'Open AML Cases',     prompt: 'Summarize all open AML cases and their current investigation status.',              agent: 'aml_agent',          icon: '🔎' },
    { label: 'SAR Filing',         prompt: 'Which customers require Suspicious Activity Reports and what are the key indicators?', agent: 'aml_agent',       icon: '📝' },
    { label: 'Transaction Screen', prompt: 'Screen recent transactions for structuring, layering, or unusual patterns.',        agent: 'aml_agent',          icon: '🔍' },
    { label: 'PEP / Sanctions',    prompt: 'Are there any PEP flags or OFAC/sanctions matches in the current customer base?',  agent: 'aml_agent',          icon: '🚨' },
    { label: 'Risk Rating',        prompt: 'What is the AML risk rating methodology and thresholds for high-risk designation?', agent: 'aml_agent',          icon: '📊' },
    { label: 'CTR Obligations',    prompt: 'Which transactions require Currency Transaction Reports under BSA requirements?',   agent: 'compliance_agent',   icon: '💵' },
  ],
  kyc_analyst: [
    { label: 'KYC Queue',          prompt: 'List all customers with pending KYC verification and missing documents.',           agent: 'kyc_agent',          icon: '🪪' },
    { label: 'Document Check',     prompt: 'What identity documents are required and which customers have expired ones?',       agent: 'kyc_agent',          icon: '📄' },
    { label: 'CDD Requirements',   prompt: 'What Customer Due Diligence requirements apply to this customer type?',            agent: 'kyc_agent',          icon: '🔍' },
    { label: 'EDD Triggers',       prompt: 'What triggers Enhanced Due Diligence and which customers currently require it?',   agent: 'kyc_agent',          icon: '⚠' },
    { label: 'KYC Policy',         prompt: 'What is the KYC refresh policy and re-verification schedule?',                     agent: 'policy_agent',       icon: '📋' },
    { label: 'Risk Classification', prompt: 'How are customers classified by risk tier and what does each tier require?',      agent: 'kyc_agent',          icon: '📊' },
  ],
  fraud_analyst: [
    { label: 'Active Fraud Alerts', prompt: 'What are all active fraud alerts ranked by risk score?',                          agent: 'fraud_detection',    icon: '🛡' },
    { label: 'Fraud Patterns',     prompt: 'Analyze recent fraud patterns — card, account takeover, and wire fraud trends.',   agent: 'fraud_detection',    icon: '📊' },
    { label: 'Transaction Anomalies', prompt: 'Identify suspicious transactions with geo-mismatch, new device, or velocity flags.', agent: 'fraud_detection', icon: '🔍' },
    { label: 'Incident Report',    prompt: 'Help me draft a fraud incident report for the current case.',                      agent: 'fraud_detection',    icon: '📝' },
    { label: 'Customer Risk',      prompt: 'What is the fraud risk profile for this customer based on their history?',         agent: 'fraud_detection',    icon: '⚠' },
    { label: 'Fraud Thresholds',   prompt: 'What are the fraud detection thresholds and escalation procedures?',               agent: 'policy_agent',       icon: '📋' },
  ],
  commercial_banker: [
    { label: 'Commercial Overview', prompt: 'Give me a commercial portfolio overview — key clients, credit exposure, and risk.', agent: 'executive_insights', icon: '🏢' },
    { label: 'Client Profile',     prompt: 'Provide a full commercial client 360 — financials, relationship, and risk profile.', agent: 'customer_360',      icon: '👤' },
    { label: 'Credit Facility',    prompt: 'Analyze the credit facility structure, covenants, and compliance status.',          agent: 'loan_decision',      icon: '💳' },
    { label: 'Risk Exposure',      prompt: 'What is the current credit risk exposure and concentration in this sector?',        agent: 'risk_analysis',      icon: '📊' },
    { label: 'Loan Covenants',     prompt: 'Review loan covenant compliance status and any covenant breach risks.',             agent: 'loan_decision',      icon: '📋' },
    { label: 'Relationship Notes', prompt: 'Summarize recent relationship interactions and follow-up action items.',           agent: 'customer_360',       icon: '📝' },
  ],
  credit_risk_analyst: [
    { label: 'Credit Scoring',     prompt: 'Explain the credit scoring model and key variables driving the current score.',    agent: 'risk_analysis',      icon: '💳' },
    { label: 'Portfolio Risk',     prompt: 'What is the current credit risk profile of the portfolio by segment and rating?',  agent: 'risk_analysis',      icon: '📊' },
    { label: 'High-Risk Customers', prompt: 'List the highest credit-risk customers and the recommended actions.',             agent: 'risk_analysis',      icon: '⚠' },
    { label: 'Stress Testing',     prompt: 'Describe the credit stress test scenarios and how the portfolio holds up.',        agent: 'risk_analysis',      icon: '🔢' },
    { label: 'PD & LGD',           prompt: 'What are the Probability of Default and Loss Given Default assumptions?',         agent: 'risk_analysis',      icon: '📈' },
    { label: 'Regulatory Capital', prompt: 'What are the risk-weighted asset calculations and capital adequacy requirements?', agent: 'compliance_agent',   icon: '⚖' },
  ],
  operations_specialist: [
    { label: 'Wire Limits',        prompt: 'What are the current wire transfer limits, cutoff times, and fee schedules?',      agent: 'treasury_agent',     icon: '💸' },
    { label: 'Transaction Status', prompt: 'Check for any failed or pending wire transfers that need investigation.',          agent: 'customer_360',       icon: '🔍' },
    { label: 'Operations Policy',  prompt: 'What are the operational procedures for wire transfers and ACH payments?',         agent: 'policy_agent',       icon: '📋' },
    { label: 'Account Issues',     prompt: 'Are there any accounts with operational flags or processing errors?',              agent: 'customer_360',       icon: '⚙' },
    { label: 'Cutoff Times',       prompt: 'What are the SWIFT, Fedwire, and CHIPS cutoff times for same-day settlement?',    agent: 'treasury_agent',     icon: '⏰' },
    { label: 'Compliance Checks',  prompt: 'What compliance steps are required for international wire transfers?',             agent: 'compliance_agent',   icon: '⚖' },
  ],
  treasury_analyst: [
    { label: 'Liquidity Position', prompt: 'What is the current liquidity position and LCR status?',                          agent: 'treasury_agent',     icon: '💰' },
    { label: 'Cash Forecast',      prompt: 'Provide a cash flow forecast and expected funding needs for the next 30 days.',   agent: 'treasury_agent',     icon: '📈' },
    { label: 'Investment Portfolio', prompt: 'Review the investment securities portfolio and duration risk.',                  agent: 'treasury_agent',     icon: '📊' },
    { label: 'Funding Sources',    prompt: 'What are the available funding sources and their costs and availability?',        agent: 'treasury_agent',     icon: '🏦' },
    { label: 'Interest Rate Risk', prompt: 'Analyze interest rate risk exposure and hedge recommendations.',                  agent: 'treasury_agent',     icon: '📉' },
    { label: 'Regulatory Ratios',  prompt: 'What are the current LCR, NSFR, and HQLA ratios versus regulatory minimums?',   agent: 'compliance_agent',   icon: '⚖' },
  ],
  executive: [
    { label: 'Portfolio Summary',  prompt: 'Give me an executive summary of the full portfolio — health, risk, and growth.',  agent: 'executive_insights', icon: '✦' },
    { label: 'Risk Dashboard',     prompt: 'What are the top enterprise risks and their current mitigation status?',          agent: 'risk_analysis',      icon: '📊' },
    { label: 'Fraud Overview',     prompt: 'What is the current fraud exposure and trend versus last quarter?',               agent: 'fraud_detection',    icon: '🛡' },
    { label: 'Loan Portfolio',     prompt: 'Summarize loan portfolio performance — NPLs, approvals, and quality metrics.',   agent: 'loan_decision',      icon: '📋' },
    { label: 'Strategic KPIs',     prompt: 'What are the key strategic KPIs and how are we tracking against targets?',       agent: 'executive_insights', icon: '🎯' },
    { label: 'Regulatory Status',  prompt: 'What is the current regulatory compliance status and any upcoming examinations?', agent: 'compliance_agent',   icon: '⚖' },
  ],
};

interface ChatInterfaceProps {
  agentId?: AgentId;
  customerId?: string;
  customer?: CustomerSummary | null;
  onShowDocs?: () => void;
  onOpenFraud?: () => void;
  onClearCustomer?: () => void;
  role?: string;
  initialMessages?: ChatMessage[];
  onMessagesUpdate?: (msgs: ChatMessage[]) => void;
  onClear?: () => void;
}

export default function ChatInterface({ agentId, customerId, customer, onShowDocs, onOpenFraud, onClearCustomer, role, initialMessages, onMessagesUpdate, onClear }: ChatInterfaceProps) {
  const effectiveCustomerId = customerId ?? customer?.customer_id;
  const [messages, setMessages]   = useState<ChatMessage[]>(initialMessages ?? []);
  const [status, setStatus]       = useState<'online' | 'thinking' | 'offline'>('online');
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeAgent, setActiveAgent] = useState<AgentId | undefined>(agentId);
  const [kpiStats, setKpiStats] = useState<KpiStats | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortStreamRef = useRef<(() => void) | null>(null);
  const user = Auth.getUser();

  // Notify parent when messages settle (skip during streaming to reduce writes)
  useEffect(() => {
    if (!isStreaming && messages.length > 0) onMessagesUpdate?.(messages);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, isStreaming]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    kpiApi.stats().then(setKpiStats).catch(() => {});
  }, []);

  const send = (text: string, overrideAgent?: AgentId) => {
    // Abort any in-progress stream
    abortStreamRef.current?.();

    const userMsg: ChatMessage = { id: nextId(), role: 'user', content: text, timestamp: Date.now() };
    const asstId = nextId();
    setMessages(prev => [...prev, userMsg, { id: asstId, role: 'assistant', content: '', timestamp: Date.now() }]);
    setStatus('thinking');
    setIsStreaming(false);

    const agent = overrideAgent ?? activeAgent;

    abortStreamRef.current = chatApi.streamSend(
      text,
      agent,
      effectiveCustomerId,
      // onToken
      (token) => {
        setIsStreaming(true);
        setMessages(prev => prev.map(m =>
          m.id === asstId ? { ...m, content: m.content + token } : m
        ));
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
      },
      // onDone
      (result: ChatResult) => {
        setMessages(prev => prev.map(m =>
          m.id === asstId ? {
            ...m,
            content: result.answer,
            sources: result.sources as ChatMessage['sources'],
            confidence: result.confidence,
            agent_name: result.agent_name,
            latency_ms: result.latency_ms,
            trust_score: result.trust_score as ChatMessage['trust_score'] ?? undefined,
          } : m
        ));
        setStatus('online');
        setIsStreaming(false);
      },
      // onError
      (err) => {
        setMessages(prev => prev.map(m =>
          m.id === asstId ? { ...m, content: `Error: ${err}` } : m
        ));
        setStatus('online');
        setIsStreaming(false);
      },
    );
  };

  const handleQuickAction = (qa: QuickAction) => {
    setActiveAgent(qa.agent);
    send(qa.prompt, qa.agent);
  };

  type KpiStrip = { key: keyof KpiStats; label: string; icon: string; clickable?: boolean };
  const ROLE_STRIP: Record<string, KpiStrip[]> = {
    admin:              [{ key: 'fraud_open', label: 'Open Fraud', icon: '🛡', clickable: true }, { key: 'total_customers', label: 'Customers', icon: '👥' }, { key: 'loan_pending', label: 'Loans Pending', icon: '📋' }, { key: 'aml_open', label: 'AML Open', icon: '🔎' }],
    fraud_analyst:      [{ key: 'fraud_open', label: 'Open Alerts', icon: '🛡', clickable: true }, { key: 'fraud_critical', label: 'Critical', icon: '🚨', clickable: true }, { key: 'fraud_total', label: 'Total Alerts', icon: '📊', clickable: true }],
    aml_analyst:        [{ key: 'aml_open', label: 'Open Cases', icon: '🔎' }, { key: 'high_risk_customers', label: 'High Risk', icon: '⚠' }, { key: 'total_customers', label: 'Customers', icon: '👥' }],
    loan_officer:       [{ key: 'loan_pending', label: 'Pending Review', icon: '⏳' }, { key: 'loan_count', label: 'Total Loans', icon: '📋' }, { key: 'avg_credit_score', label: 'Avg Credit', icon: '💳' }],
    kyc_analyst:        [{ key: 'kyc_pending', label: 'KYC Pending', icon: '🪪' }, { key: 'high_risk_customers', label: 'High Risk', icon: '⚠' }, { key: 'total_customers', label: 'Customers', icon: '👥' }],
    personal_banker:    [{ key: 'total_customers', label: 'Customers', icon: '👥' }, { key: 'kyc_pending', label: 'Pending KYC', icon: '🪪' }, { key: 'trust_score_avg', label: 'Trust Avg', icon: '✦' }],
    branch_manager:     [{ key: 'fraud_open', label: 'Open Fraud', icon: '🛡', clickable: true }, { key: 'loan_pending', label: 'Loans Pending', icon: '📋' }, { key: 'total_customers', label: 'Customers', icon: '👥' }],
    executive:          [{ key: 'total_customers', label: 'Customers', icon: '👥' }, { key: 'loan_count', label: 'Active Loans', icon: '📋' }, { key: 'trust_score_avg', label: 'Trust Avg', icon: '✦' }],
    credit_risk_analyst:[{ key: 'avg_credit_score', label: 'Avg Credit', icon: '💳' }, { key: 'high_risk_customers', label: 'High Risk', icon: '⚠' }, { key: 'loan_count', label: 'Active Loans', icon: '📋' }],
    treasury_analyst:   [{ key: 'loan_count', label: 'Active Loans', icon: '📋' }, { key: 'total_customers', label: 'Customers', icon: '👥' }, { key: 'ai_queries_today', label: 'AI Queries', icon: '⚡' }],
  };
  const strip = ROLE_STRIP[role ?? ''] ?? ROLE_STRIP.personal_banker;

  const fmtKpi = (key: keyof KpiStats, val: number | undefined): string => {
    if (val === undefined || val === null) return '—';
    if (key === 'trust_score_avg') return val.toFixed(1);
    if (key === 'avg_credit_score') return val.toLocaleString();
    return Number(val).toLocaleString();
  };

  const persona = ROLE_PERSONA[role ?? ''] ?? ROLE_PERSONA.personal_banker;
  const quickActions: QuickAction[] = ROLE_QUICK_ACTIONS[role ?? ''] ?? ROLE_QUICK_ACTIONS.personal_banker;

  return (
    <GlassCard animate={false} className="flex flex-col h-full min-h-0 rounded-none border-y-0 border-r-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/[0.06]">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <div className={`w-7 h-7 rounded-lg bg-gradient-to-br ${persona.gradient} flex items-center justify-center text-sm shadow-glow-sm`}>
              {persona.icon}
            </div>
            <span className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-green-400 border border-[#0c0c14] animate-pulse-glow" />
          </div>
          <div>
            <div className="text-xs font-semibold text-t1">{persona.name}</div>
            {customer ? (
              <div className="flex items-center gap-1.5 text-[10px] text-t3">
                <span>Context: {customer.name}</span>
                {onClearCustomer && (
                  <button onClick={onClearCustomer}
                    className="text-purple-300/70 hover:text-red-400 transition-colors"
                    title="Clear customer context">× clear</button>
                )}
              </div>
            ) : (
              <div className="text-[10px] text-t3">{persona.description}</div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <button
              onClick={() => onClear ? onClear() : setMessages([])}
              className="text-[10px] text-t3 hover:text-purple-300 transition-colors px-2 py-1 rounded-lg border border-white/[0.06] hover:border-purple-500/20"
              title="Start a new conversation">
              + New
            </button>
          )}
          <AIStatusBadge status={status} />
        </div>
      </div>

      {/* Role-aware KPI Strip */}
      {kpiStats && (
        <div className="flex gap-1 px-3 py-1.5 border-b border-white/[0.04] overflow-x-auto bg-white/[0.01]">
          {strip.map(item => {
            const val = kpiStats[item.key] as number | undefined;
            const isClickable = item.clickable && onOpenFraud;
            return (
              <button
                key={item.key}
                onClick={isClickable ? onOpenFraud : undefined}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg flex-shrink-0 transition-all text-left ${
                  isClickable
                    ? 'bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 cursor-pointer'
                    : 'bg-white/[0.03] border border-white/[0.06] cursor-default'
                }`}
              >
                <span className="text-[11px]">{item.icon}</span>
                <div>
                  <div className={`text-[11px] font-bold tabular-nums leading-none ${
                    isClickable ? 'text-red-400' : 'text-t1'
                  }`}>
                    {fmtKpi(item.key, val)}
                  </div>
                  <div className="text-[8px] text-t3 leading-none mt-0.5">{item.label}</div>
                </div>
                {isClickable && (
                  <span className="text-[8px] text-red-400/60 ml-0.5">↗</span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 min-h-0">
        <div className="flex flex-col justify-end min-h-full space-y-1">
        {messages.length === 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center h-full gap-6 text-center py-8">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-purple-500/20 flex items-center justify-center text-2xl shadow-glow-sm">
              ✦
            </div>
            <div>
              <h3 className="text-base font-semibold gradient-text mb-1.5">Banking Intelligence Ready</h3>
              <p className="text-xs text-t3 max-w-xs">
                {user?.role_label ? `${user.role_label} copilot` : 'Ask about customers, risk, compliance, or policies.'}
              </p>
            </div>

            {/* Quick Actions Grid */}
            <div className="grid grid-cols-3 gap-2 w-full max-w-lg">
              {quickActions.map((qa: QuickAction) => (
                <motion.button
                  key={qa.label}
                  whileHover={{ y: -2 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => handleQuickAction(qa)}
                  className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-white/[0.04] border border-white/[0.06] hover:border-purple-500/20 hover:bg-purple-500/[0.06] transition-all text-center"
                >
                  <span className="text-base">{qa.icon}</span>
                  <span className="text-[10px] text-t2 font-medium leading-tight">{qa.label}</span>
                </motion.button>
              ))}
            </div>
          </motion.div>
        )}

        {/* Group messages into Q+A pairs with date separators */}
        {messages.length > 0 && (() => {
          // Build exchange pairs: each user msg + following assistant msg
          const pairs: { userMsg: ChatMessage; asstMsg?: ChatMessage; date: string }[] = [];
          let lastDate = '';
          for (let i = 0; i < messages.length; i++) {
            const m = messages[i];
            if (m.role === 'user') {
              const dateStr = new Date(m.timestamp).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
              const asst = messages[i + 1]?.role === 'assistant' ? messages[i + 1] : undefined;
              pairs.push({ userMsg: m, asstMsg: asst, date: dateStr });
              if (asst) i++;
            }
          }
          return pairs.map((pair, pairIdx) => {
            const showDate = pair.date !== lastDate;
            lastDate = pair.date;
            const asstIdx = messages.indexOf(pair.asstMsg ?? pair.userMsg);
            const isInFlight =
              pair.asstMsg !== undefined &&
              pair.asstMsg === messages[messages.length - 1] &&
              (isStreaming || status === 'thinking');
            return (
              <div key={pair.userMsg.id}>
                {showDate && (
                  <div className="flex items-center gap-2 my-3">
                    <div className="flex-1 h-px bg-white/[0.06]" />
                    <span className="text-[9px] text-t3 px-2">{pair.date}</span>
                    <div className="flex-1 h-px bg-white/[0.06]" />
                  </div>
                )}
                {/* Highlighted exchange card */}
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, delay: pairIdx < 3 ? 0 : 0.05 }}
                  className="rounded-2xl border border-white/[0.05] bg-white/[0.02] px-3 pt-3 pb-2 mb-3 space-y-3 hover:border-purple-500/[0.12] transition-colors">
                  {/* User message */}
                  <MessageBubble
                    message={pair.userMsg}
                    index={messages.indexOf(pair.userMsg)}
                    isInFlight={false}
                  />
                  {/* Assistant response */}
                  {pair.asstMsg && (
                    <MessageBubble
                      message={pair.asstMsg}
                      index={asstIdx}
                      prompt={pair.userMsg.content}
                      isInFlight={isInFlight}
                    />
                  )}
                </motion.div>
              </div>
            );
          });
        })()}

        <div ref={bottomRef} />
        </div>
      </div>

      {/* Quick action bar (when has messages) */}
      {messages.length > 0 && (
        <div className="px-3 py-1 border-t border-white/[0.04] flex gap-1 overflow-x-auto">
          {quickActions.map((qa: QuickAction) => (
            <button key={qa.label} onClick={() => handleQuickAction(qa)}
              className="flex-shrink-0 text-[9px] px-2 py-1 rounded-md bg-white/[0.04] border border-white/[0.06] hover:border-purple-500/20 text-t3 hover:text-purple-300 transition-all">
              {qa.icon} {qa.label}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="px-3 pb-3 pt-2 border-t border-white/[0.04]">
        <ChatInput onSend={send} disabled={status === 'thinking'} onShowDocs={onShowDocs} />
      </div>
    </GlassCard>
  );
}
