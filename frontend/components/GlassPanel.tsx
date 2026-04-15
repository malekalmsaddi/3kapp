import { PropsWithChildren } from 'react';

interface GlassPanelProps extends PropsWithChildren {
  className?: string;
}

export default function GlassPanel({ children, className }: GlassPanelProps) {
  return (
    <div
      className={`rounded-2xl ${className ?? ''}`}
      style={{
        background: '#ffffff',
        border: '1px solid rgba(0,0,0,0.07)',
        boxShadow: '0 1px 3px rgba(0,0,0,0.06), 0 4px 20px rgba(0,0,0,0.04)',
        padding: '1.5rem',
      }}
    >
      {children}
    </div>
  );
}
