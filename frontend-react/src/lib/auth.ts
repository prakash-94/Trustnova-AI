import type { User } from '@/types/banking';

const TOKEN_KEY = 'tn_token';
const USER_KEY  = 'tn_user';

export const Auth = {
  setSession({ token, user }: { token: string; user: User }) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  },
  getUser(): User | null {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try { return JSON.parse(raw) as User; } catch { return null; }
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
  isAuthenticated(): boolean {
    return !!this.getToken() && !!this.getUser();
  },
  hasNavSection(section: string): boolean {
    const user = this.getUser();
    if (!user) return false;
    const sections = user.nav_sections ?? [];
    return sections.includes('all') || sections.includes(section);
  },
  hasPermission(permission: string): boolean {
    const user = this.getUser();
    if (!user) return false;
    const perms = user.permissions ?? [];
    if (perms.includes('*') || perms.includes(permission)) return true;
    const prefix = permission.split(':')[0];
    return perms.includes(`${prefix}:all`) || perms.includes(`${prefix}:*`);
  },
};
