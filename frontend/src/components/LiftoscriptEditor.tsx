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
Plank / 3x6 10s rest 5s after 30s
Pigeon Stretch / 1x2 60s ~
Rower / 1x1 2000m
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
        {!error && (
          <span title="Timing goes after NxM: work per rep (10s, 2min, 1:30), rest between reps (rest 5s), rest after the set (after 30s). Distance: 400m, 5km, 1mi, 100yd. m is metres; minutes are min or m:ss. Add ~ to flag a spec's sets as mobility work. Anything else on a line is an error.">
            Timing: 10s rest 5s after 30s · distance: 400m · mobility: ~
          </span>
        )}
        {error && (
          <span style={{ color: 'var(--error)', fontFamily: 'var(--font-body)' }}>
            {error}
          </span>
        )}
      </div>
    </div>
  );
}
