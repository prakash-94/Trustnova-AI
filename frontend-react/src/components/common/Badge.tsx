type BadgeColor = 'purple' | 'blue' | 'green' | 'amber' | 'red' | 'orange' | 'gray' | 'cyan' | 'slate';

interface BadgeProps {
  label: string;
  color?: BadgeColor;
  dot?: boolean;
  className?: string;
}

const COLOR_MAP: Record<BadgeColor, string> = {
  purple: 'bg-purple-500/15 text-purple-300 border-purple-500/25',
  blue:   'bg-blue-500/15   text-blue-300   border-blue-500/25',
  green:  'bg-green-500/15  text-green-300  border-green-500/25',
  amber:  'bg-amber-500/15  text-amber-300  border-amber-500/25',
  red:    'bg-red-500/15    text-red-300    border-red-500/25',
  orange: 'bg-orange-500/15 text-orange-300 border-orange-500/25',
  gray:   'bg-white/[0.06]  text-white/50   border-white/[0.08]',
  cyan:   'bg-cyan-500/15   text-cyan-300   border-cyan-500/25',
  slate:  'bg-slate-500/15  text-slate-300  border-slate-500/25',
};

const DOT_MAP: Record<BadgeColor, string> = {
  purple: 'bg-purple-400',
  blue:   'bg-blue-400',
  green:  'bg-green-400',
  amber:  'bg-amber-400',
  red:    'bg-red-400',
  orange: 'bg-orange-400',
  gray:   'bg-white/40',
  cyan:   'bg-cyan-400',
  slate:  'bg-slate-400',
};

export default function Badge({ label, color = 'gray', dot = false, className = '' }: BadgeProps) {
  const colors = COLOR_MAP[color] ?? COLOR_MAP.gray;
  const dotColor = DOT_MAP[color] ?? DOT_MAP.gray;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border capitalize ${colors} ${className}`}>
      {dot && <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotColor}`} />}
      {label}
    </span>
  );
}
