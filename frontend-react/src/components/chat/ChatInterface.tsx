import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { chatApi } from '@/lib/api';
import GlassCard from '@/components/ui/GlassCard';

interface Msg { role: 'user' | 'assistant'; content: string; sources?: any[]; trust?: number; }

const STARTERS = [
  'What are our mortgage rates?',
  'Explain AML red flags',
  'How do I open a business account?',
  'What is the wire transfer fee?',
];

export default function ChatInterface() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs]);

  const send = async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg: Msg = { role: 'user', content: text };
    setMsgs(m => [...m, userMsg]);
    setInput('');
    setLoading(true);
    try {
      const r = await chatApi.send(text, msgs.map(m => ({ role: m.role, content: m.content })));
      setMsgs(m => [...m, { role: 'assistant', content: r.response ?? r.message ?? '...', sources: r.sources, trust: r.trust_score }]);
    } catch (e: any) {
      setMsgs(m => [...m, { role: 'assistant', content: `Error: ${e.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full p-6">
      <div className="mb-4">
        <h1 className="text-xl font-bold gradient-text">AI Banking Copilot</h1>
        <p className="text-white/40 text-sm">Ask about products, policies, compliance, customers</p>
      </div>

      <GlassCard className="flex-1 flex flex-col min-h-0 p-0 overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {msgs.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center gap-6 py-12">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center text-3xl shadow-glow-md"
                style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>✦</div>
              <div className="text-center">
                <div className="text-white/70 font-medium">How can I help you today?</div>
                <div className="text-white/30 text-sm mt-1">Your AI banking assistant</div>
              </div>
              <div className="grid grid-cols-2 gap-2 w-full max-w-md">
                {STARTERS.map(s => (
                  <button key={s} onClick={() => send(s)}
                    className="text-xs text-left px-3 py-2 rounded-xl text-white/50 hover:text-white/80 hover:bg-white/5 border border-white/8 transition-all">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          <AnimatePresence initial={false}>
            {msgs.map((m, i) => (
              <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-purple-600/30 border border-purple-500/20 text-white/90'
                    : 'glass-card text-white/80'
                }`}>
                  <div className="whitespace-pre-wrap">{m.content}</div>
                  {m.trust !== undefined && (
                    <div className="mt-2 pt-2 border-t border-white/10 text-xs text-white/30">
                      Trust: {Math.round(m.trust * 100)}% · {m.sources?.length ?? 0} sources
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {loading && (
            <div className="flex justify-start">
              <div className="glass-card px-4 py-3 rounded-2xl">
                <div className="flex gap-1">
                  {[0,1,2].map(i => (
                    <motion.div key={i} className="w-1.5 h-1.5 rounded-full bg-purple-400"
                      animate={{ opacity: [0.3, 1, 0.3] }}
                      transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }} />
                  ))}
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="p-3 border-t border-white/6">
          <form onSubmit={e => { e.preventDefault(); send(input); }} className="flex gap-2">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="Ask anything..."
              className="flex-1 px-4 py-2.5 text-sm"
            />
            <button type="submit" disabled={!input.trim() || loading}
              className="px-4 py-2.5 rounded-xl text-sm font-medium text-white disabled:opacity-40 transition-all"
              style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
              Send
            </button>
          </form>
        </div>
      </GlassCard>
    </div>
  );
}
