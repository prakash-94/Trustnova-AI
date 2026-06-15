import { motion } from 'framer-motion';

interface Props { status: 'online' | 'thinking' | 'offline'; }

const CONFIG = {
  online:   { dot: 'bg-green-400 animate-pulse-glow', label: 'AI Ready',   text: 'text-green-400'  },
  thinking: { dot: 'bg-amber-400 animate-pulse',      label: 'Thinking…',  text: 'text-amber-400'  },
  offline:  { dot: 'bg-red-400',                      label: 'Offline',    text: 'text-red-400'    },
};

export default function AIStatusBadge({ status }: Props) {
  const c = CONFIG[status];
  return (
    <motion.div
      key={status}
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/[0.04] border border-white/[0.08]"
    >
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${c.dot}`} />
      <span className={`text-[10px] font-medium ${c.text}`}>{c.label}</span>
    </motion.div>
  );
}
