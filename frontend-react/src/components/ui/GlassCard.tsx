import { ReactNode } from 'react';
import clsx from 'clsx';

interface Props {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  hover?: boolean;
}

export default function GlassCard({ children, className, onClick, hover }: Props) {
  return (
    <div
      onClick={onClick}
      className={clsx(
        'glass-card p-4',
        hover && 'cursor-pointer hover:border-purple-500/30 hover:shadow-glow-sm transition-all duration-200',
        onClick && 'cursor-pointer',
        className
      )}
    >
      {children}
    </div>
  );
}
