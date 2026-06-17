import type { ChatMessage } from '@/types/banking';

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
}

const BASE_KEY = 'trusnova_conversations';
const MAX_CONVERSATIONS = 60;

function storeKey(username?: string): string {
  return username ? `${BASE_KEY}_${username}` : BASE_KEY;
}

export function loadConversations(username?: string): Conversation[] {
  const key = storeKey(username);
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw) as Conversation[];
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {}

  // For named users: migrate any existing shared history on first load, then clear shared
  if (username) {
    try {
      const shared = localStorage.getItem(BASE_KEY);
      if (shared) {
        const parsed = JSON.parse(shared) as Conversation[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          saveConversations(parsed, username);
          localStorage.removeItem(BASE_KEY);
          return parsed;
        }
      }
    } catch {}
  }

  // Migrate from old flat format
  try {
    const oldRaw = localStorage.getItem('trusnova_chat_history');
    if (oldRaw) {
      const oldMessages = JSON.parse(oldRaw) as ChatMessage[];
      const completed = oldMessages.filter(m => m.role === 'user' || m.content.length > 0);
      if (completed.length > 0) {
        const migrated = makeConversation(completed);
        saveConversations([migrated], username);
        localStorage.removeItem('trusnova_chat_history');
        return [migrated];
      }
    }
  } catch {}

  return [];
}

export function saveConversations(convs: Conversation[], username?: string): void {
  try {
    const sorted = [...convs].sort((a, b) => b.updatedAt - a.updatedAt);
    localStorage.setItem(storeKey(username), JSON.stringify(sorted.slice(0, MAX_CONVERSATIONS)));
  } catch {}
}

export function makeConversation(messages: ChatMessage[] = []): Conversation {
  return {
    id: `conv_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    title: getTitleFromMessages(messages),
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messages,
  };
}

export function getTitleFromMessages(messages: ChatMessage[]): string {
  const firstUser = messages.find(m => m.role === 'user');
  if (!firstUser?.content) return 'New Conversation';
  const t = firstUser.content.trim();
  return t.length > 42 ? t.slice(0, 42) + '…' : t;
}

export function groupConversationsByDate(
  convs: Conversation[],
): { label: string; items: Conversation[] }[] {
  const sorted = [...convs].sort((a, b) => b.updatedAt - a.updatedAt);

  const now = new Date();
  const todayStart = new Date(now); todayStart.setHours(0, 0, 0, 0);
  const yesterdayStart = new Date(todayStart); yesterdayStart.setDate(yesterdayStart.getDate() - 1);
  const weekStart = new Date(todayStart); weekStart.setDate(weekStart.getDate() - 7);
  const monthStart = new Date(todayStart); monthStart.setDate(monthStart.getDate() - 30);

  const groups: { label: string; items: Conversation[] }[] = [
    { label: 'Today', items: [] },
    { label: 'Yesterday', items: [] },
    { label: 'Previous 7 Days', items: [] },
    { label: 'Previous 30 Days', items: [] },
    { label: 'Older', items: [] },
  ];

  for (const conv of sorted) {
    const d = conv.updatedAt;
    if (d >= todayStart.getTime()) groups[0].items.push(conv);
    else if (d >= yesterdayStart.getTime()) groups[1].items.push(conv);
    else if (d >= weekStart.getTime()) groups[2].items.push(conv);
    else if (d >= monthStart.getTime()) groups[3].items.push(conv);
    else groups[4].items.push(conv);
  }

  return groups.filter(g => g.items.length > 0);
}
