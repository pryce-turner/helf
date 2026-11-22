import { useEffect, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { ArrowRight, Calendar as CalendarIcon, Check, FileCode, Pencil, Trash2, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { presetsApi } from '@/lib/api';
import { DayEditor } from './WorkoutSession';
import Navigation from '@/components/Navigation';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { usePresetTileSource } from '@/hooks/useTileSource';
import { formatDuration, timedWorkSeconds } from '@/lib/setTiles';
import {
  useApplyWorkoutPreset,
  useDeleteWorkoutPreset,
  useRenameWorkoutPreset,
  useWorkoutPreset,
} from '@/hooks/useWorkoutPresets';

/**
 * One block of yours on the day editor (plans 0020, 0022) - a block is what
 * was a preset: part of a day, applied to one or pulled into a program with
 * `[Its name]`. "Script" shows exactly what that line puts in.
 *
 * Tiles save as they are added, edited, reordered or deleted — the same as a
 * day — so there is no Save for them; the name is the one thing saved here.
 * A brand-new preset opens with its name ready to type over.
 */
const PresetEditor = () => {
  const { id } = useParams<{ id: string }>();
  const presetId = Number(id);
  const navigate = useNavigate();
  const location = useLocation();
  const isNew = Boolean((location.state as { isNew?: boolean } | null)?.isNew);

  const { data: preset, isError } = useWorkoutPreset(presetId);
  const source = usePresetTileSource(presetId);
  const renamePreset = useRenameWorkoutPreset();
  const deletePreset = useDeleteWorkoutPreset();
  const applyPreset = useApplyWorkoutPreset();

  const [editingName, setEditingName] = useState(isNew);
  // Null until typed into: the field shows the saved name, so nothing has to
  // copy it into state when the preset arrives.
  const [draftName, setDraftName] = useState<string | null>(null);
  const [nameError, setNameError] = useState('');
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [showApply, setShowApply] = useState(false);
  const [showScript, setShowScript] = useState(false);
  const script = useQuery({
    queryKey: ['workout-presets', presetId, 'script', preset?.updated_at],
    queryFn: async () => (await presetsApi.getScript(presetId)).data.script,
    enabled: showScript && !!preset,
  });
  const [applyDate, setApplyDate] = useState<Date | undefined>(new Date());

  // A two-tap delete, disarmed after a moment, like a tile's.
  useEffect(() => {
    if (!confirmingDelete) return;
    const timer = setTimeout(() => setConfirmingDelete(false), 3000);
    return () => clearTimeout(timer);
  }, [confirmingDelete]);

  const closeName = () => {
    setDraftName(null);
    setNameError('');
    setEditingName(false);
  };

  const saveName = async () => {
    if (!preset) return;
    const trimmed = (draftName ?? preset.name).trim();
    if (!trimmed) {
      setNameError('A block needs a name');
      return;
    }
    if (trimmed !== preset.name) {
      try {
        await renamePreset.mutateAsync({ id: preset.doc_id, name: trimmed });
      } catch (error: unknown) {
        const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setNameError(typeof detail === 'string' ? detail : 'Could not rename the block');
        return;
      }
    }
    closeName();
  };

  const handleApply = async () => {
    if (!preset || !applyDate) return;
    const date = format(applyDate, 'yyyy-MM-dd');
    await applyPreset.mutateAsync({ id: preset.doc_id, date });
    navigate(`/day/${date}`);
  };

  const handleDelete = async () => {
    if (!preset) return;
    await deletePreset.mutateAsync(preset.doc_id);
    navigate('/library');
  };

  if (isError || Number.isNaN(presetId)) {
    return (
      <>
        <Navigation />
        <div className="page">
          <div className="page__content page__content--narrow">
            <p style={{ color: 'var(--text-muted)' }}>This block does not exist.</p>
            <Button variant="secondary" onClick={() => navigate('/library')} style={{ marginTop: 'var(--space-4)' }}>
              Back to the library
            </Button>
          </div>
        </div>
      </>
    );
  }

  const setCount = preset?.items.length ?? 0;
  const timedSeconds = timedWorkSeconds(source.tiles ?? []);

  const title = editingName ? (
    <span className="flex items-center" style={{ gap: 'var(--space-2)' }}>
      <Input
        aria-label="Block name"
        value={draftName ?? preset?.name ?? ''}
        autoFocus
        onFocus={(e) => isNew && e.currentTarget.select()}
        onChange={(e) => {
          setDraftName(e.target.value);
          setNameError('');
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') saveName();
          if (e.key === 'Escape') closeName();
        }}
        style={{ fontSize: '18px', maxWidth: '320px' }}
      />
      <button type="button" className="action-btn" onClick={saveName} aria-label="Save name" title="Save name">
        <Check style={{ width: '16px', height: '16px' }} />
      </button>
    </span>
  ) : (
    <span className="flex items-center" style={{ gap: 'var(--space-2)' }}>
      {preset?.name ?? ''}
      {preset && (
        <button
          type="button"
          className="action-btn"
          onClick={() => setEditingName(true)}
          aria-label="Rename block"
          title="Rename"
        >
          <Pencil style={{ width: '16px', height: '16px' }} />
        </button>
      )}
    </span>
  );

  const subtitle = nameError ? (
    <span style={{ color: 'var(--error)' }}>{nameError}</span>
  ) : (
    `${setCount} set${setCount !== 1 ? 's' : ''}` +
    (timedSeconds > 0 ? ` · ${formatDuration(timedSeconds)} timed` : '')
  );

  const extraActions = (
    <>
      <Button variant="secondary" size="sm" onClick={() => setShowScript(!showScript)}>
        <FileCode style={{ width: '16px', height: '16px' }} />
        Script
      </Button>
      {setCount > 0 && (
        <Button variant="secondary" size="sm" onClick={() => setShowApply(!showApply)}>
          <CalendarIcon style={{ width: '16px', height: '16px' }} />
          Apply to day
        </Button>
      )}
      {confirmingDelete ? (
        <>
          <Button variant="destructive" size="sm" onClick={handleDelete} disabled={deletePreset.isPending}>
            <Check style={{ width: '16px', height: '16px' }} />
            Delete block
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setConfirmingDelete(false)} aria-label="Keep block">
            <X style={{ width: '16px', height: '16px' }} />
          </Button>
        </>
      ) : (
        <Button variant="secondary" size="sm" onClick={() => setConfirmingDelete(true)}>
          <Trash2 style={{ width: '16px', height: '16px' }} />
          Delete
        </Button>
      )}
    </>
  );

  const scriptPanel = showScript ? (
    <Card className="animate-in" style={{ marginBottom: 'var(--space-6)' }}>
      <CardContent>
        <p className="library-description" style={{ marginBottom: 'var(--space-3)' }}>
          What <code>[{preset?.name}]</code> puts into a program:
        </p>
        <pre className="script-view">{script.data ?? ''}</pre>
      </CardContent>
    </Card>
  ) : null;

  const applyPanel = showApply ? (
    <Card className="animate-in" style={{ marginBottom: 'var(--space-6)', border: '1px solid var(--border)' }}>
      <CardContent style={{ padding: 'var(--space-5)' }}>
        <p
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: '14px',
            color: 'var(--text-secondary)',
            marginBottom: 'var(--space-4)',
          }}
        >
          Apply to which day? The sets land as planned, after anything already there.
        </p>
        <Calendar
          mode="single"
          selected={applyDate}
          onSelect={setApplyDate}
          className="rounded-[var(--radius-md)] border border-[var(--border)]"
        />
        <div className="flex justify-end" style={{ marginTop: 'var(--space-4)', gap: 'var(--space-2)' }}>
          <Button variant="secondary" onClick={() => setShowApply(false)}>
            Cancel
          </Button>
          <Button onClick={handleApply} disabled={!applyDate || applyPreset.isPending}>
            <ArrowRight style={{ width: '16px', height: '16px' }} />
            Apply to {applyDate && format(applyDate, 'MMM d, yyyy')}
          </Button>
        </div>
      </CardContent>
    </Card>
  ) : null;

  const extraPanels = (
    <>
      {scriptPanel}
      {applyPanel}
    </>
  );

  return (
    <DayEditor
      source={source}
      title={title}
      subtitle={subtitle}
      onBack={() => navigate('/library')}
      extraActions={extraActions}
      extraPanels={extraPanels}
      emptyTitle="No sets yet"
      emptyText="Add the exercises this block should put on a day"
    />
  );
};

export default PresetEditor;
