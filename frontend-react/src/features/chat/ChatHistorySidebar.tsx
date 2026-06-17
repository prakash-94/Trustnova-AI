import { useState } from 'react';
import type { Conversation } from '@/services/conversations';
import { groupConversationsByDate } from '@/services/conversations';

interface Props {
  conversations: Conversation[];
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export default function ChatHistorySidebar({ conversations, activeId, onSelect, onNew, onDelete }: Props) {
  const [isOpen, setIsOpen]     = useState(true);
  const [hoverId, setHoverId]   = useState<string | null>(null);
  const groups = groupConversationsByDate(conversations);

  return (
    <div
      className={`flex-shrink-0 flex flex-col h-full rounded-2xl border border-white/[0.06] bg-white/[0.02] overflow-hidden transition-all duration-200 ease-in-out ${
        isOpen ? 'w-52' : 'w-9'
      }`}
    >
      {/* ── Header ── */}
      <div className={`flex items-center border-b border-white/[0.06] flex-shrink-0 ${
        isOpen ? 'justify-between px-3 py-2.5' : 'justify-center px-1.5 py-2.5'
      }`}>
        {isOpen && (
          <span className="text-[9px] font-semibold text-t3 uppercase tracking-widest truncate">
            Chat History
          </span>
        )}

        <div className={`flex items-center ${isOpen ? 'gap-1' : ''}`}>
          {/* Compose / New chat — only when open */}
          {isOpen && (
            <button
              onClick={onNew}
              title="New chat"
              className="w-5 h-5 flex items-center justify-center rounded hover:bg-purple-500/20 text-t3 hover:text-purple-300 transition-all"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 5H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
                <path d="m18.5 2.5 2 2L13 12l-4 1 1-4 7.5-7.5z" />
              </svg>
            </button>
          )}

          {/* Toggle collapse / expand */}
          <button
            onClick={() => setIsOpen(v => !v)}
            title={isOpen ? 'Collapse history' : 'Expand history'}
            className="w-5 h-5 flex items-center justify-center rounded hover:bg-white/[0.08] text-t3 hover:text-t1 transition-all"
          >
            {isOpen ? (
              /* chevron left (collapse) */
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            ) : (
              /* chevron right (expand) */
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* ── Collapsed strip — just show a "new chat" icon below toggle ── */}
      {!isOpen && (
        <div className="flex flex-col items-center pt-2 gap-2">
          <button
            onClick={onNew}
            title="New chat"
            className="w-6 h-6 flex items-center justify-center rounded-lg hover:bg-purple-500/20 text-t3 hover:text-purple-300 transition-all"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
              <path d="m18.5 2.5 2 2L13 12l-4 1 1-4 7.5-7.5z" />
            </svg>
          </button>
          {/* Active conversation dot indicator */}
          {conversations.length > 0 && (
            <div className="flex flex-col items-center gap-1 mt-1">
              {conversations.slice(0, 8).map(conv => (
                <button
                  key={conv.id}
                  onClick={() => onSelect(conv.id)}
                  title={conv.title}
                  className={`w-1.5 h-1.5 rounded-full transition-all ${
                    conv.id === activeId ? 'bg-purple-400' : 'bg-white/20 hover:bg-white/40'
                  }`}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Expanded conversation list ── */}
      {isOpen && (
        <div className="flex-1 overflow-y-auto py-1 px-1.5 space-y-0.5 min-h-0">
          {conversations.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full px-4 text-center gap-3 py-8">
              <div className="w-9 h-9 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-base">
                💬
              </div>
              <p className="text-[10px] text-t3 leading-relaxed">
                No conversations yet.<br />Ask anything to begin.
              </p>
              <button
                onClick={onNew}
                className="text-[10px] px-3 py-1.5 rounded-lg bg-purple-500/15 border border-purple-500/20 text-purple-300 hover:bg-purple-500/25 transition-all"
              >
                + New Chat
              </button>
            </div>
          ) : (
            groups.map(group => (
              <div key={group.label}>
                <p className="text-[8px] text-t3/60 uppercase tracking-wider px-2 pt-2.5 pb-1 select-none">
                  {group.label}
                </p>
                {group.items.map(conv => {
                  const isActive  = conv.id === activeId;
                  const isHovered = hoverId === conv.id;
                  return (
                    <div
                      key={conv.id}
                      onMouseEnter={() => setHoverId(conv.id)}
                      onMouseLeave={() => setHoverId(null)}
                      onClick={() => onSelect(conv.id)}
                      className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg cursor-pointer transition-all ${
                        isActive
                          ? 'bg-purple-500/15 border border-purple-500/25'
                          : 'border border-transparent hover:bg-white/[0.04]'
                      }`}
                    >
                      <span className="text-[10px] flex-shrink-0 opacity-60">
                        {isActive ? '✦' : '💬'}
                      </span>
                      <span
                        className={`flex-1 text-[11px] truncate leading-snug min-w-0 ${
                          isActive ? 'text-purple-300 font-medium' : 'text-t2'
                        }`}
                      >
                        {conv.title}
                      </span>
                      {/* Delete on hover */}
                      {isHovered && (
                        <button
                          onClick={e => { e.stopPropagation(); onDelete(conv.id); }}
                          title="Delete conversation"
                          className="flex-shrink-0 w-4 h-4 flex items-center justify-center rounded text-t3 hover:text-red-400 hover:bg-red-500/10 transition-all"
                        >
                          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <polyline points="3,6 5,6 21,6" />
                            <path d="M19,6 18,20H6L5,6" />
                            <path d="M10,11v6M14,11v6M9,6V4h6v2" />
                          </svg>
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
