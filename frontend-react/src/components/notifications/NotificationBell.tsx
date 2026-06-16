import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { notificationsApi } from '@/lib/api';
import type { AppNotification } from '@/lib/api';

const TYPE_ICON: Record<string, string> = {
  announcement:    '📢',
  access_request:  '🔐',
  access_approved: '✅',
  access_denied:   '❌',
  bug_report:      '🐛',
  bug_update:      '🔧',
  account_created: '👤',
};

const PRIORITY_BORDER: Record<string, string> = {
  urgent:    'border-red-500/40',
  important: 'border-amber-500/40',
  normal:    'border-purple-500/20',
};

export default function NotificationBell() {
  const [items, setItems]         = useState<AppNotification[]>([]);
  const [unread, setUnread]       = useState(0);
  const [open, setOpen]           = useState(false);
  const [popup, setPopup]         = useState<AppNotification | null>(null);
  const dropRef                   = useRef<HTMLDivElement>(null);
  const shownIds                  = useRef<Set<number>>(new Set());

  const fetchAll = useCallback(async () => {
    try {
      const r = await notificationsApi.list(false, 40);
      setItems(r.notifications);
      setUnread(r.unread_count);

      // Show popup for unread announcements AND access requests we haven't shown yet
      const POPUP_TYPES = new Set(['announcement', 'access_request']);
      const newPopup = r.notifications.find(
        n => POPUP_TYPES.has(n.type) && !n.is_read && !shownIds.current.has(n.id)
      );
      if (newPopup && !open) {
        setPopup(newPopup);
        shownIds.current.add(newPopup.id);
      }
      // Track all read ids so we don't re-show them
      r.notifications.forEach(n => { if (n.is_read) shownIds.current.add(n.id); });
    } catch { /* ignore — user may not be logged in yet */ }
  }, [open]);

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, 30_000);
    return () => clearInterval(t);
  }, [fetchAll]);

  // Close dropdown on outside click
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const markOne = async (id: number) => {
    await notificationsApi.markRead([id]).catch(() => {});
    setItems(prev => prev.map(n => n.id === id ? { ...n, is_read: 1 } : n));
    setUnread(prev => Math.max(0, prev - 1));
    shownIds.current.add(id);
  };

  const markAll = async () => {
    await notificationsApi.markRead().catch(() => {});
    setItems(prev => prev.map(n => ({ ...n, is_read: 1 })));
    setUnread(0);
  };

  const dismissPopup = async () => {
    if (popup) {
      await markOne(popup.id);
      setPopup(null);
    }
  };

  // Parse priority from a notification title prefix
  const getPriority = (n: AppNotification) => {
    if (n.title.startsWith('🚨')) return 'urgent';
    if (n.title.startsWith('⚠'))  return 'important';
    return 'normal';
  };

  return (
    <>
      {/* ── Notification popup banner ─────────────────────────────────────── */}
      <AnimatePresence>
        {popup && (
          <motion.div
            initial={{ opacity: 0, y: -16, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -16, scale: 0.97 }}
            transition={{ duration: 0.25 }}
            className="fixed top-16 left-1/2 -translate-x-1/2 z-[60] w-full max-w-md px-4"
          >
            <div className={`glass-card border ${
              popup.type === 'access_request'
                ? 'border-amber-500/40'
                : PRIORITY_BORDER[getPriority(popup)]
            } px-5 py-4 shadow-xl`}>
              <div className="flex items-start gap-3">
                <div className="text-xl flex-shrink-0 mt-0.5">
                  {TYPE_ICON[popup.type] ?? '📋'}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-t1 leading-snug">{popup.title}</p>
                  <p className="text-[11px] text-t3 mt-1 leading-relaxed line-clamp-4">{popup.body}</p>
                </div>
                <button
                  onClick={dismissPopup}
                  className="flex-shrink-0 text-t3 hover:text-t1 transition-colors w-5 h-5 flex items-center justify-center text-base"
                >✕</button>
              </div>
              <div className="mt-2.5 flex gap-2 justify-end">
                {popup.type === 'access_request' && (
                  <button
                    onClick={() => {
                      dismissPopup();
                      window.dispatchEvent(new CustomEvent('tn:navigate', { detail: { section: 'access_requests' } }));
                    }}
                    className="text-[10px] px-3 py-1 rounded-lg bg-amber-500/15 border border-amber-500/25 text-amber-300 hover:bg-amber-500/25 transition-all"
                  >
                    View Requests
                  </button>
                )}
                <button
                  onClick={dismissPopup}
                  className="text-[10px] px-3 py-1 rounded-lg bg-purple-500/15 border border-purple-500/25 text-purple-300 hover:bg-purple-500/25 transition-all"
                >
                  Got it
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Bell icon + dropdown ──────────────────────────────────────────── */}
      <div className="relative" ref={dropRef}>
        <motion.button
          whileTap={{ scale: 0.9 }}
          onClick={() => setOpen(o => !o)}
          className="relative w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white/[0.06] text-t2 hover:text-t1 transition-all"
          title="Notifications"
        >
          <span className="text-base">🔔</span>
          {unread > 0 && (
            <span className="absolute top-0.5 right-0.5 w-4 h-4 rounded-full bg-red-500 text-[8px] font-bold text-white flex items-center justify-center leading-none">
              {unread > 9 ? '9+' : unread}
            </span>
          )}
        </motion.button>

        <AnimatePresence>
          {open && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -4 }}
              transition={{ duration: 0.15 }}
              className="absolute right-0 top-10 w-80 glass-card border border-white/[0.08] shadow-xl z-50 overflow-hidden"
            >
              {/* Header */}
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.06]">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-t1">Notifications</span>
                  {unread > 0 && (
                    <span className="px-1.5 py-0.5 rounded-full bg-red-500/20 text-red-400 text-[9px] font-bold">
                      {unread} new
                    </span>
                  )}
                </div>
                {unread > 0 && (
                  <button onClick={markAll}
                    className="text-[10px] text-purple-400 hover:text-purple-300 transition-colors">
                    Mark all read
                  </button>
                )}
              </div>

              {/* List */}
              <div className="max-h-80 overflow-y-auto">
                {items.length === 0 ? (
                  <div className="px-4 py-10 text-center">
                    <div className="text-2xl mb-2">🔔</div>
                    <p className="text-xs text-t3">No notifications yet</p>
                  </div>
                ) : (
                  items.map(n => (
                    <button
                      key={n.id}
                      onClick={() => { if (!n.is_read) markOne(n.id); }}
                      className={`w-full text-left px-4 py-2.5 border-b border-white/[0.03] hover:bg-white/[0.03] transition-colors flex gap-2.5 ${!n.is_read ? 'bg-purple-500/[0.04]' : ''}`}
                    >
                      <span className="text-sm flex-shrink-0 mt-0.5">{TYPE_ICON[n.type] ?? '📋'}</span>
                      <div className="flex-1 min-w-0">
                        <p className={`text-xs leading-tight ${!n.is_read ? 'text-t1 font-medium' : 'text-t2'}`}>
                          {n.title}
                        </p>
                        {n.body && (
                          <p className="text-[10px] text-t3 mt-0.5 line-clamp-2 leading-relaxed">{n.body}</p>
                        )}
                        <p className="text-[9px] text-t3/40 mt-1 font-mono">
                          {n.created_at.slice(0, 16).replace('T', ' ')}
                        </p>
                      </div>
                      {!n.is_read && (
                        <span className="w-1.5 h-1.5 rounded-full bg-purple-400 flex-shrink-0 mt-1.5" />
                      )}
                    </button>
                  ))
                )}
              </div>

              <div className="px-4 py-2 border-t border-white/[0.04] text-[9px] text-t3/50 text-center">
                Refreshes every 30s
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
}
