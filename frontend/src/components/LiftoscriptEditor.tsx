import { useMemo } from 'react';

interface LiftoscriptEditorProps {
  value: string;
  onChange: (value: string) => void;
  error?: string;
}

export default function LiftoscriptEditor({ value, onChange, error }: LiftoscriptEditorProps) {
  const stats = useMemo(() => {
    const lines = value.split('\n').length;
    const chars = value.length;
    return { lines, chars };
  }, [value]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="# Week 1
## Squat Day
// Main Lift
Barbell Squat / 1x5 65%, 1x5 75%, 1x5+ 85%
..."
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '14px',
          lineHeight: '1.6',
          background: 'var(--bg-tertiary)',
          border: error ? '1px solid var(--error)' : '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: 'var(--space-4)',
          color: 'var(--text-primary)',
          resize: 'vertical',
          minHeight: '300px',
          width: '100%',
          boxSizing: 'border-box',
          outline: 'none',
        }}
        onFocus={(e) => {
          if (!error) {
            e.target.style.borderColor = 'var(--accent)';
            e.target.style.boxShadow = '0 0 0 3px var(--accent-glow)';
          }
        }}
        onBlur={(e) => {
          e.target.style.borderColor = error ? 'var(--error)' : 'var(--border)';
          e.target.style.boxShadow = 'none';
        }}
      />
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        fontSize: '12px',
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
      }}>
        <span>{stats.lines} lines, {stats.chars.toLocaleString()} characters</span>
        {error && (
          <span style={{ color: 'var(--error)', fontFamily: 'var(--font-body)' }}>
            {error}
          </span>
        )}
      </div>
    </div>
  );
}
