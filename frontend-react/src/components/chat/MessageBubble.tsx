import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';
import TrustGauge from '@/components/ui/TrustGauge';
import { feedbackApi } from '@/lib/api';
import type { ChatMessage } from '@/types/banking';

interface MessageBubbleProps {
  message: ChatMessage;
  index: number;
  prompt?: string;
  isInFlight?: boolean;
}

const COMPONENT_LABELS: Record<string, { label: string; invert?: boolean }> = {
  retrieval_confidence:     { label: 'Retrieval Confidence' },
  hallucination_probability:{ label: 'Hallucination Risk', invert: true },
  model_agreement:          { label: 'Model Agreement' },
  citation_quality:         { label: 'Citation Quality' },
  prompt_reliability:       { label: 'Prompt Reliability' },
};

const confBand = (c: number): { label: string; color: string; bg: string; border: string } =>
  c >= 0.75
    ? { label: 'High', color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/20' }
    : c >= 0.45
    ? { label: 'Medium', color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/20' }
    : { label: 'Low', color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20' };

// Detect and render markdown tables in the response text
function renderContent(text: string) {
  const lines = text.split('\n');
  const result: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    if (lines[i].includes('|') && i + 1 < lines.length && /^\|?[\s-|]+\|?$/.test(lines[i + 1])) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].includes('|')) {
        tableLines.push(lines[i]);
        i++;
      }
      result.push(<MarkdownTable key={`tbl-${i}`} lines={tableLines} />);
      continue;
    }

    const line = lines[i].replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    if (line.trim().startsWith('**') || line.trim().startsWith('#')) {
      result.push(
        <p key={i} className="text-[11px] font-semibold text-t1 mt-2 mb-0.5"
          dangerouslySetInnerHTML={{ __html: line.replace(/^#+\s*/, '').replace(/\*\*/g, '') }} />
      );
    } else if (line.trim().startsWith('- ') || line.trim().startsWith('• ')) {
      result.push(
        <li key={i} className="text-[11px] text-t1 ml-3 list-disc leading-snug"
          dangerouslySetInnerHTML={{ __html: line.replace(/^[-•]\s*/, '') }} />
      );
    } else if (line.trim()) {
      result.push(
        <p key={i} className="text-[11px] text-t1 leading-snug"
          dangerouslySetInnerHTML={{ __html: line }} />
      );
    } else {
      result.push(<div key={i} className="h-1" />);
    }
    i++;
  }
  return result;
}

function MarkdownTable({ lines }: { lines: string[] }) {
  const parse = (line: string) =>
    line.split('|').map(c => c.trim()).filter((c, i, arr) => !(i === 0 && c === '') && !(i === arr.length - 1 && c === ''));

  const [header, , ...dataRows] = lines;
  const headers = parse(header);
  const rows = dataRows.map(parse);

  return (
    <div className="my-2 overflow-x-auto rounded-xl border border-white/[0.08]">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-white/[0.08] bg-white/[0.03]">
            {headers.map((h, i) => (
              <th key={i} className="px-3 py-2 text-left text-[10px] text-t3 uppercase tracking-wider font-semibold whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/[0.04]">
          {rows.map((row, ri) => (
            <tr key={ri} className="hover:bg-white/[0.02] transition-colors">
              {row.map((cell, ci) => (
                <td key={ci} className="px-3 py-2 text-t2 whitespace-nowrap"
                  dangerouslySetInnerHTML={{ __html: cell.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') }} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type FeedbackState = 'idle' | 'editing' | 'submitted';

export default function MessageBubble({ message, index, prompt, isInFlight = false }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const [showTrust, setShowTrust] = useState(false);
  const [feedbackState, setFeedbackState] = useState<FeedbackState>('idle');
  const [feedbackType, setFeedbackType] = useState<'approve' | 'reject' | 'edit' | null>(null);
  const [editText, setEditText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const ts = message.trust_score;
  const conf = message.confidence;
  const band = conf !== undefined ? confBand(conf) : null;

  const submitFeedback = async (type: 'approve' | 'reject' | 'edit', correction?: string) => {
    setSubmitting(true);
    try {
      await feedbackApi.submitResponse({
        response_id: message.id,
        feedback_type: type,
        prompt: prompt ?? '',
        response_text: message.content,
        correction_text: correction,
        trust_score: ts?.final_score,
        session_id: 'chat',
      });
      setFeedbackState('submitted');
      setFeedbackType(type);
    } catch {
      // still mark as submitted visually
      setFeedbackState('submitted');
      setFeedbackType(type);
    } finally {
      setSubmitting(false);
    }
  };

  const handleApprove = () => submitFeedback('approve');
  const handleReject = () => submitFeedback('reject');
  const handleEditSubmit = () => {
    if (editText.trim()) submitFeedback('edit', editText.trim());
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, delay: index * 0.03, ease: [0.16, 1, 0.3, 1] }}
      className={clsx('flex gap-3', isUser ? 'flex-row-reverse' : 'flex-row')}
    >
      {/* Avatar */}
      <div className={clsx(
        'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold',
        isUser
          ? 'bg-gradient-to-br from-purple-500 to-blue-500 text-white'
          : 'bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-purple-500/30 text-purple-300',
      )}>
        {isUser ? 'U' : '✦'}
      </div>

      {/* Bubble + meta */}
      <div className={clsx('max-w-[82%] group', isUser ? 'items-end' : 'items-start')}>
        <div className={clsx(
          'px-3 py-2 rounded-2xl',
          isUser
            ? 'bg-purple-500/20 border border-purple-500/25 text-t1 rounded-tr-sm text-xs leading-snug'
            : 'glass border border-white/[0.06] text-t1 rounded-tl-sm',
        )}>
          {isUser ? (
            <span className="text-xs">{message.content}</span>
          ) : (
            <div className="space-y-1">{renderContent(message.content)}</div>
          )}
        </div>

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {message.sources.map((s, i) => (
              <span key={i} className="text-xs px-2 py-0.5 rounded-md bg-blue-500/10 border border-blue-500/20 text-blue-300">
                📄 {s.document}{s.page !== undefined && ` p.${s.page}`}
              </span>
            ))}
          </div>
        )}

        {/* Confidence badge + AI Trust Score */}
        {!isUser && (band || ts) && (
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            {band && (
              <div className={clsx(
                'flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full border',
                band.bg, band.border, band.color,
              )}>
                <span className="w-1.5 h-1.5 rounded-full bg-current inline-block" />
                {band.label} Confidence
                <span className="font-normal text-[10px] opacity-70">({Math.round((conf ?? 0) * 100)}%)</span>
              </div>
            )}

            {ts && (
              <button
                onClick={() => setShowTrust(v => !v)}
                className={clsx(
                  'flex items-center gap-1.5 text-[10px] font-semibold px-2 py-1 rounded-full border transition-all',
                  ts.final_score >= 71 ? 'bg-green-500/10 border-green-500/20 text-green-400 hover:bg-green-500/15'
                  : ts.final_score >= 41 ? 'bg-amber-500/10 border-amber-500/20 text-amber-400 hover:bg-amber-500/15'
                  : 'bg-red-500/10 border-red-500/20 text-red-400 hover:bg-red-500/15'
                )}
              >
                <span>✦</span>
                AI Trust {Math.round(ts.final_score)}/100
                <span className={clsx('transition-transform duration-200', showTrust ? 'rotate-180' : '')}>▾</span>
              </button>
            )}

            {message.latency_ms && (
              <span className="text-[10px] text-t3">{message.latency_ms}ms</span>
            )}
          </div>
        )}

        {/* Confidence only — no trust score */}
        {!isUser && !ts && !band && conf !== undefined && (
          <div className="mt-1.5 text-xs text-t3 flex items-center gap-1">
            <span className={clsx('inline-block w-1.5 h-1.5 rounded-full',
              conf >= 0.75 ? 'bg-green-400' : conf >= 0.45 ? 'bg-amber-400' : 'bg-red-400'
            )} />
            {Math.round(conf * 100)}% confidence
          </div>
        )}

        {/* AI Trust Score breakdown */}
        <AnimatePresence>
          {!isUser && ts && showTrust && (
            <motion.div
              initial={{ opacity: 0, height: 0, y: -4 }}
              animate={{ opacity: 1, height: 'auto', y: 0 }}
              exit={{ opacity: 0, height: 0, y: -4 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className="mt-2 overflow-hidden"
            >
              <div className="glass border border-white/[0.06] rounded-xl p-3 flex gap-4">
                <TrustGauge score={ts.final_score} tier={ts.tier} size="sm" />
                <div className="flex-1 space-y-2">
                  <p className="text-[9px] text-t3 mb-1">
                    AI Trust Score measures answer quality — high score = retrieved from policy documents with strong citations.
                  </p>
                  {Object.entries(ts.components).map(([key, raw]) => {
                    const cfg = COMPONENT_LABELS[key];
                    const display = cfg?.invert ? 1 - raw : raw;
                    const pct = Math.round(display * 100);
                    const barColor = pct >= 70 ? 'bg-green-400' : pct >= 40 ? 'bg-amber-400' : 'bg-red-400';
                    return (
                      <div key={key}>
                        <div className="flex justify-between text-[9px] mb-0.5">
                          <span className="text-t3">{cfg?.label ?? key}</span>
                          <span className="text-t2">{pct}%</span>
                        </div>
                        <div className="w-full h-1 rounded-full bg-white/[0.06]">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${pct}%` }}
                            transition={{ duration: 0.6, ease: 'easeOut' }}
                            className={clsx('h-full rounded-full', barColor)}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Approve / Reject / Edit feedback row — only after response is fully built */}
        {!isUser && !isInFlight && message.content.length > 0 && (
          <AnimatePresence>
            {feedbackState === 'submitted' ? (
              <motion.div key="done" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="mt-2 flex items-center gap-1.5 text-[10px] text-t3">
                <span className={
                  feedbackType === 'approve' ? 'text-green-400' :
                  feedbackType === 'reject' ? 'text-red-400' : 'text-blue-400'
                }>
                  {feedbackType === 'approve' ? '✓ Approved' : feedbackType === 'reject' ? '✗ Rejected' : '✎ Edited'}
                </span>
                <span>— feedback logged</span>
              </motion.div>
            ) : (
              <motion.div key="actions" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="mt-2 space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <button onClick={handleApprove} disabled={submitting}
                    title="Approve this answer"
                    className="text-[10px] px-2 py-0.5 rounded-md bg-green-500/10 border border-green-500/20 text-green-400 hover:bg-green-500/15 transition-all disabled:opacity-40">
                    ✓ Approve
                  </button>
                  <button onClick={handleReject} disabled={submitting}
                    title="Mark this answer as incorrect"
                    className="text-[10px] px-2 py-0.5 rounded-md bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/15 transition-all disabled:opacity-40">
                    ✗ Reject
                  </button>
                  <button onClick={() => setFeedbackState(s => s === 'editing' ? 'idle' : 'editing')} disabled={submitting}
                    title="Suggest a correction"
                    className="text-[10px] px-2 py-0.5 rounded-md bg-blue-500/10 border border-blue-500/20 text-blue-400 hover:bg-blue-500/15 transition-all disabled:opacity-40">
                    ✎ Edit
                  </button>
                </div>

                <AnimatePresence>
                  {feedbackState === 'editing' && (
                    <motion.div key="edit-box"
                      initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.2 }}
                      className="overflow-hidden">
                      <textarea
                        value={editText}
                        onChange={e => setEditText(e.target.value)}
                        rows={2}
                        placeholder="Enter the correct answer or correction…"
                        className="w-full mt-1 px-3 py-2 text-[11px] rounded-lg bg-white/[0.04] border border-white/[0.08] text-t1 placeholder-t3 focus:outline-none focus:border-blue-500/40 resize-none"
                      />
                      <button onClick={handleEditSubmit} disabled={!editText.trim() || submitting}
                        className="mt-1 text-[10px] px-3 py-1 rounded-md bg-blue-500/15 border border-blue-500/25 text-blue-300 hover:bg-blue-500/20 transition-all disabled:opacity-40">
                        Submit correction
                      </button>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            )}
          </AnimatePresence>
        )}

        {/* Timestamp */}
        <div className="text-xs text-t3 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          {!isUser && message.agent_name && <span className="ml-1.5 text-purple-400/60">{message.agent_name}</span>}
        </div>
      </div>
    </motion.div>
  );
}
