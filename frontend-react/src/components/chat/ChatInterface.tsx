import { useState, useRef, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { chatApi, kpiApi, type ChatResult, type KpiStats } from '@/lib/api';
import { Auth } from '@/lib/auth';
import GlassCard from '@/components/ui/GlassCard';
import AIStatusBadge from './AIStatusBadge';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import type { ChatMessage, AgentId } from '@/types/banking';
import type { CustomerSummary } from '@/types';

let msgIdCounter = Date.now(); // start high to avoid collisions across mounts
const nextId = () => String(++msgIdCounter);

const QUICK_ACTIONS: { label: string; prompt: string; agent: AgentId; icon: string }[] = [
  { label: 'Customer Summary',  prompt: 'Give me a summary of our top customers and their risk profiles.',         agent: 'customer_360',      icon: '👤' },
  { label: 'Risk Assessment',   prompt: 'What are the current high-risk customers and recommended actions?',       agent: 'risk_analysis',     icon: '📊' },
  { label: 'AML Review',        prompt: 'Summarize open AML cases and any SAR filing requirements.',               agent: 'aml_agent',         icon: '🔎' },
  { label: 'Fraud Analysis',    prompt: 'What are the active fraud alerts and detection patterns?',                agent: 'fraud_detection',   icon: '🛡' },
  { label: 'KYC Status',        prompt: 'Which customers have pending KYC and what documents are missing?',       agent: 'kyc_agent',         icon: '🪪' },
  { label: 'Loan Eligibility',  prompt: 'What are our current loan approval criteria and DTI thresholds?',        agent: 'loan_decision',     icon: '📋' },
  { label: 'Wire Limits',       prompt: 'What are the current wire transfer limits and cutoff times?',            agent: 'treasury_agent',    icon: '💸' },
  { label: 'Compliance Check',  prompt: 'What compliance obligations are due this month?',                        agent: 'compliance_agent',  icon: '⚖' },
  { label: 'Portfolio Summary', prompt: 'Give me an executive summary of our portfolio health and key metrics.',  agent: 'executive_insights',icon: '✦' },
];

interface ChatInterfaceProps {
  agentId?: AgentId;
  customerId?: string;
  customer?: CustomerSummary | null;
  onShowDocs?: () => void;
  onOpenFraud?: () => void;
  role?: string;
  initialMessages?: ChatMessage[];
  onMessagesUpdate?: (msgs: ChatMessage[]) => void;
  onClear?: () => void;
}

export default function ChatInterface({ agentId, customerId, customer, onShowDocs, onOpenFraud, role, initialMessages, onMessagesUpdate, onClear }: ChatInterfaceProps) {
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

  const handleQuickAction = (qa: typeof QUICK_ACTIONS[0]) => {
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

  return (
    <GlassCard animate={false} className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/[0.06]">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-purple-500 to-blue-600 flex items-center justify-center text-sm shadow-glow-sm">
              ✦
            </div>
            <span className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-green-400 border border-[#0c0c14] animate-pulse-glow" />
          </div>
          <div>
            <div className="text-xs font-semibold text-t1">TrustNova Copilot</div>
            <div className="text-[10px] text-t3">
              {customer ? `Context: ${customer.name}` : activeAgent ? activeAgent.replace(/_/g, ' ') : 'Llama 3.3 70B · 10 Agents'}
            </div>
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
              {QUICK_ACTIONS.map(qa => (
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

        {status === 'thinking' && !isStreaming && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3 items-end">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-purple-500/30 flex items-center justify-center text-xs text-purple-300">
              ✦
            </div>
            <div className="glass px-4 py-3 rounded-2xl rounded-tl-sm border border-white/[0.06]">
              <span className="flex gap-1">
                {[0, 1, 2].map(i => (
                  <motion.span key={i} className="w-1.5 h-1.5 rounded-full bg-purple-400"
                    animate={{ y: [-3, 3, -3] }} transition={{ duration: 0.7, delay: i * 0.15, repeat: Infinity }} />
                ))}
              </span>
            </div>
          </motion.div>
        )}

        <div ref={bottomRef} />
        </div>
      </div>

      {/* Quick action bar (when has messages) */}
      {messages.length > 0 && (
        <div className="px-3 py-1 border-t border-white/[0.04] flex gap-1 overflow-x-auto">
          {QUICK_ACTIONS.map(qa => (
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
