import { useState, useRef, type KeyboardEvent } from 'react';
import { motion } from 'framer-motion';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
  onShowDocs?: () => void;
}

export default function ChatInput({ onSend, disabled, placeholder, onShowDocs }: ChatInputProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  return (
    <div className="glass-card p-1 flex items-end gap-2 !rounded-2xl">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={e => { setValue(e.target.value); handleInput(); }}
        onKeyDown={handleKey}
        rows={1}
        disabled={disabled}
        placeholder={placeholder ?? 'Ask anything about your customers, transactions, or policies…'}
        className="flex-1 resize-none bg-transparent border-0 text-xs text-t1 px-3 py-2
                   placeholder-t3 focus:outline-none focus:ring-0 leading-normal
                   disabled:opacity-40 min-h-[36px] max-h-40"
        style={{ boxShadow: 'none' }}
      />
      <motion.button
        whileTap={{ scale: 0.93 }}
        onClick={submit}
        disabled={disabled || !value.trim()}
        className="flex-shrink-0 mb-1 mr-1 w-8 h-8 rounded-xl flex items-center justify-center
                   bg-purple-500 hover:bg-purple-600 text-white text-sm
                   shadow-glow-sm hover:shadow-glow-md
                   disabled:opacity-40 disabled:cursor-not-allowed
                   transition-all duration-200"
      >
        {disabled ? (
          <span className="w-3.5 h-3.5 border-2 border-white/60 border-t-white rounded-full animate-spin" />
        ) : '↑'}
      </motion.button>
    </div>
  );
}
