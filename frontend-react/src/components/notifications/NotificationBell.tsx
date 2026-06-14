import { useState, useEffect, useRef } from 'react';
import { notificationsApi } from '@/lib/api';
import { motion, AnimatePresence } from 'framer-motion';

interface Props { onNav: (id: string) => void; }

export default function NotificationBell({ onNav }: Props) {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState<any[]>([]);
  const [unread, setUnread] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  const load = async () => {
    try {
      const r = await notificationsApi.list();
      setNotes(r.notifications ?? []);
      setUnread(r.unread_count ?? 0);
    } catch {}
  };

  useEffect(() => { load(); const id = setInterval(load, 30000); return () => clearInterval(id); }, []);

  useEffect(() => {
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const markAll = async () => { await notificationsApi.markAllRead(); setUnread(0); setNotes(n => n.map(x => ({ ...x, is_read: 1 }))); };

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(o => !o)}
        className="relative w-8 h-8 flex items-center justify-center rounded-lg text-white/50 hover:text-white hover:bg-white/8 transition-all">
        🔔
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-purple-500 text-white text-xs flex items-center justify-center font-bold">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 top-10 w-80 glass-card shadow-glow-md z-50 overflow-hidden"
          >
            <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <span className="text-sm font-semibold text-white/80">Notifications</span>
              {unread > 0 && <button onClick={markAll} className="text-xs text-purple-400 hover:text-purple-300">Mark all read</button>}
            </div>
            <div className="overflow-y-auto max-h-72">
              {notes.length === 0 ? (
                <div className="px-4 py-6 text-center text-white/30 text-sm">No notifications</div>
              ) : notes.slice(0, 10).map(n => (
                <div key={n.id} className={`px-4 py-3 text-sm border-b border-white/5 ${!n.is_read ? 'bg-purple-500/5' : ''}`}>
                  <div className="font-medium text-white/80">{n.title}</div>
                  <div className="text-white/40 text-xs mt-0.5">{n.message}</div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
