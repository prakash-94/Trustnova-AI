import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { bugReportsApi } from '@/services/api';

interface Props { onClose: () => void; }

type ReportType = 'feedback' | 'bug' | 'suggestion';
type Priority   = 'low' | 'medium' | 'high' | 'critical';

const TYPE_OPTIONS: { value: ReportType; label: string; icon: string; desc: string }[] = [
  { value: 'bug',        icon: '🐛', label: 'Bug Report',  desc: 'Something is broken or not working as expected' },
  { value: 'feedback',   icon: '💬', label: 'Feedback',    desc: 'General feedback about the platform' },
  { value: 'suggestion', icon: '💡', label: 'Suggestion',  desc: 'Idea or improvement request' },
];

const PRIORITY_OPTIONS: { value: Priority; label: string; color: string }[] = [
  { value: 'low',      label: 'Low',      color: 'text-blue-400 bg-blue-500/10 border-blue-500/20' },
  { value: 'medium',   label: 'Medium',   color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' },
  { value: 'high',     label: 'High',     color: 'text-orange-400 bg-orange-500/10 border-orange-500/20' },
  { value: 'critical', label: 'Critical', color: 'text-red-400 bg-red-500/10 border-red-500/20' },
];

export default function FeedbackBugModal({ onClose }: Props) {
  const [type, setType]           = useState<ReportType>('feedback');
  const [title, setTitle]         = useState('');
  const [description, setDesc]    = useState('');
  const [priority, setPriority]   = useState<Priority>('medium');
  const [loading, setLoading]     = useState(false);
  const [success, setSuccess]     = useState(false);
  const [error, setError]         = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!title.trim() || !description.trim()) {
      setError('Title and description are required.');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await bugReportsApi.create({ type, title: title.trim(), description: description.trim(), priority });
      setSuccess(true);
      setTimeout(onClose, 2200);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Submit failed. Try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <motion.div
        initial={{ scale: 0.94, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.94, opacity: 0 }} transition={{ duration: 0.2 }}
        className="glass-card w-full max-w-lg overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
          <div>
            <h2 className="text-sm font-semibold text-t1">Submit Feedback or Report</h2>
            <p className="text-[10px] text-t3 mt-0.5">Help us improve TrustNova AI</p>
          </div>
          <button onClick={onClose}
            className="text-t3 hover:text-t1 w-7 h-7 flex items-center justify-center rounded-lg hover:bg-white/[0.06] transition-all text-lg">
            ✕
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Success state */}
          <AnimatePresence>
            {success && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center py-8 text-center gap-3"
              >
                <div className="text-4xl">✅</div>
                <p className="text-sm font-semibold text-t1">Submitted!</p>
                <p className="text-xs text-t3">Admin has been notified. Closing…</p>
              </motion.div>
            )}
          </AnimatePresence>

          {!success && (
            <>
              {/* Type selector */}
              <div>
                <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-2 block">Type</label>
                <div className="grid grid-cols-3 gap-2">
                  {TYPE_OPTIONS.map(opt => (
                    <button key={opt.value} onClick={() => setType(opt.value)}
                      className={`flex flex-col items-center gap-1 px-2 py-3 rounded-xl border text-center transition-all text-xs ${
                        type === opt.value
                          ? 'border-purple-500/40 bg-purple-500/10 text-purple-300'
                          : 'border-white/[0.07] text-t3 hover:border-white/[0.12] hover:text-t2'
                      }`}>
                      <span className="text-lg">{opt.icon}</span>
                      <span className="font-medium text-[10px]">{opt.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Title */}
              <div>
                <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Title</label>
                <input
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  placeholder={type === 'bug' ? 'e.g. Fraud modal crashes on open' : 'Brief summary…'}
                  maxLength={120}
                  className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 transition-colors"
                />
              </div>

              {/* Description */}
              <div>
                <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Description</label>
                <textarea
                  value={description}
                  onChange={e => setDesc(e.target.value)}
                  rows={4}
                  placeholder={
                    type === 'bug'
                      ? 'Steps to reproduce, expected vs actual behavior…'
                      : 'Describe your feedback or suggestion in detail…'
                  }
                  maxLength={1000}
                  className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-purple-500/40 transition-colors resize-none"
                />
                <p className="text-[9px] text-t3/50 mt-1 text-right">{description.length}/1000</p>
              </div>

              {/* Priority */}
              <div>
                <label className="text-[10px] text-t3 uppercase tracking-wider font-medium mb-1.5 block">Priority</label>
                <div className="flex gap-2">
                  {PRIORITY_OPTIONS.map(opt => (
                    <button key={opt.value} onClick={() => setPriority(opt.value)}
                      className={`flex-1 py-1.5 rounded-lg border text-[10px] font-medium transition-all ${
                        priority === opt.value ? opt.color : 'border-white/[0.07] text-t3 hover:text-t2'
                      }`}>
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Error */}
              {error && (
                <p className="text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              {/* Submit */}
              <div className="flex gap-2 pt-1">
                <button onClick={onClose}
                  className="flex-1 py-2.5 rounded-xl border border-white/[0.08] text-xs text-t3 hover:text-t1 hover:border-white/[0.12] transition-all">
                  Cancel
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={loading || !title.trim() || !description.trim()}
                  className="flex-1 py-2.5 rounded-xl bg-purple-500/20 border border-purple-500/30 text-xs text-purple-300 font-medium hover:bg-purple-500/30 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {loading ? 'Submitting…' : 'Submit Report'}
                </button>
              </div>
            </>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
