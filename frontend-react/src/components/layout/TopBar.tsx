import { Auth } from '@/lib/auth';
import NotificationBell from '@/components/notifications/NotificationBell';

interface Props {
  onToggleSidebar: () => void;
  onLogout: () => void;
  onNav: (id: string) => void;
}

export default function TopBar({ onToggleSidebar, onLogout, onNav }: Props) {
  const user = Auth.getUser();

  return (
    <header className="flex items-center justify-between px-5 h-14 flex-shrink-0"
      style={{ background: 'rgba(7,7,15,0.9)', borderBottom: '1px solid rgba(255,255,255,0.06)', backdropFilter: 'blur(12px)' }}>
      <div className="flex items-center gap-3">
        <button onClick={onToggleSidebar}
          className="w-8 h-8 flex items-center justify-center rounded-lg text-white/50 hover:text-white hover:bg-white/8 transition-all">
          ☰
        </button>
        <div className="hidden sm:flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse-glow" />
          <span className="text-xs text-white/40">Live</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <NotificationBell onNav={onNav} />
        <button
          onClick={onLogout}
          className="text-xs text-white/40 hover:text-white/70 px-3 py-1.5 rounded-lg hover:bg-white/5 transition-all"
        >
          Logout
        </button>
        {user && (
          <div className="hidden sm:flex items-center gap-2">
            <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold"
              style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
              {user.full_name?.[0] ?? 'U'}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
