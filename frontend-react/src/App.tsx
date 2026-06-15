import { useState, useEffect } from 'react';
import { Auth } from '@/lib/auth';
import LoginPage from '@/pages/LoginPage';
import BankerCopilot from '@/pages/BankerCopilot';

export default function App() {
  const [authed, setAuthed] = useState(Auth.isAuthenticated());

  useEffect(() => {
    const handler = () => setAuthed(Auth.isAuthenticated());
    window.addEventListener('auth-change', handler);
    return () => window.removeEventListener('auth-change', handler);
  }, []);

  if (!authed) return <LoginPage onLogin={() => setAuthed(true)} />;
  const user = Auth.getUser()!;
  return <BankerCopilot user={user} onLogout={() => { Auth.clear(); setAuthed(false); }} />;
}
