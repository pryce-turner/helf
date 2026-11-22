import { useNavigate } from 'react-router-dom';
import { ChevronRight, Plus, ScrollText } from 'lucide-react';
import Navigation from '@/components/Navigation';
import WorkoutSectionTabs from '@/components/WorkoutSectionTabs';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useCreateWorkoutPreset, useWorkoutPresets } from '@/hooks/useWorkoutPresets';
import type { WorkoutPreset } from '@/types/preset';

/** "Squat, Bench Press, Plank" — each movement once, in the order it comes. */
const movementSummary = (preset: WorkoutPreset) =>
  [...new Set([...preset.items].sort((a, b) => a.order - b.order).map((i) => i.exercise))].join(', ');

/**
 * Hand-built presets (plan 0020), a tab of the Workouts section.
 *
 * A preset is made on the same editor as a day and applied to one as planned
 * sets. Add creates an empty one straight away and opens it, so there is no
 * separate "name it first" step — it starts as "New preset" and is renamed on
 * the editor.
 */
const Presets = () => {
  const navigate = useNavigate();
  const { data: presets, isLoading } = useWorkoutPresets();
  const createPreset = useCreateWorkoutPreset();

  const handleAdd = async () => {
    const preset = await createPreset.mutateAsync(undefined);
    navigate(`/presets/${preset.doc_id}`, { state: { isNew: true } });
  };

  return (
    <>
      <Navigation />
      <div className="page">
        <div className="page__content page__content--narrow">
          <div className="page__header animate-in">
            <div className="flex items-start justify-between flex-wrap" style={{ gap: 'var(--space-4)' }}>
              <div>
                <h1 className="page__title">Preset</h1>
                <p className="page__subtitle">Workouts you build by hand and reuse</p>
              </div>
              <Button onClick={handleAdd} disabled={createPreset.isPending}>
                <Plus style={{ width: '16px', height: '16px' }} />
                Add preset
              </Button>
            </div>
          </div>

          <WorkoutSectionTabs />

          {isLoading ? (
            <div className="text-center" style={{ padding: 'var(--space-16) 0' }}>
              <div className="loading-spinner inline-block" />
            </div>
          ) : presets && presets.length > 0 ? (
            <div className="stagger-children" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              {presets.map((preset) => (
                <Card key={preset.doc_id} className="card-hover animate-in">
                  <button
                    type="button"
                    onClick={() => navigate(`/presets/${preset.doc_id}`)}
                    className="flex items-center justify-between w-full"
                    style={{
                      gap: 'var(--space-4)',
                      padding: 'var(--space-5)',
                      background: 'none',
                      border: 'none',
                      color: 'inherit',
                      textAlign: 'left',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '17px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {preset.name}
                      </div>
                      <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                        {preset.items.length} set{preset.items.length !== 1 ? 's' : ''}
                        {preset.items.length > 0 ? ` · ${movementSummary(preset)}` : ''}
                      </p>
                    </div>
                    <ChevronRight style={{ width: '16px', height: '16px', color: 'var(--text-muted)', flexShrink: 0 }} />
                  </button>
                </Card>
              ))}
            </div>
          ) : (
            <Card style={{ border: '2px dashed var(--border)', background: 'transparent' }}>
              <CardContent className="empty-state">
                <div className="empty-state__icon">
                  <ScrollText style={{ width: '40px', height: '40px', color: 'var(--text-muted)' }} />
                </div>
                <h3 className="empty-state__title">No presets yet</h3>
                <p className="empty-state__text">Build a workout once, then apply it to any day.</p>
                <Button onClick={handleAdd} disabled={createPreset.isPending}>
                  <Plus style={{ width: '16px', height: '16px' }} />
                  Add preset
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </>
  );
};

export default Presets;
