import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowDown, ArrowLeft, ArrowUp, Check, FileCode, Pencil, Play, Plus, Trash2, X } from 'lucide-react';
import Navigation from '@/components/Navigation';
import ExerciseSearch from '@/components/ExerciseSearch';
import LiftoscriptEditor from '@/components/LiftoscriptEditor';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { libraryApi } from '@/lib/api';
import { buildScript, conflictingMaxes } from '@/lib/programBuilder';
import { useExercises } from '@/hooks/useExercises';
import { useDeleteProgram, useLibrary, useProgram, useUpdateProgram } from '@/hooks/useLibrary';
import type { BuilderItem, BuilderModel, Program, ScriptCheck } from '@/types/library';

type CheckState = { ok: true; result: ScriptCheck } | { ok: false; error: string } | null;

/** Parses the script on the server as you edit - blocks and all - so a typo
 *  shows here, not as a failed Generate. Debounced; setState only in the
 *  request's callback. */
function useScriptCheck(script: string): CheckState {
  const [state, setState] = useState<CheckState>(null);
  useEffect(() => {
    const timer = setTimeout(() => {
      libraryApi
        .check(script)
        .then((r) => setState({ ok: true, result: r.data }))
        .catch((e: { response?: { data?: { detail?: string } } }) =>
          setState({ ok: false, error: e?.response?.data?.detail ?? 'Could not check the script' }),
        );
    }, 500);
    return () => clearTimeout(timer);
  }, [script]);
  return state;
}

const CheckLine = ({ check }: { check: CheckState }) =>
  check === null ? null : check.ok ? (
    <p className="program-check program-check--ok">
      {check.result.sessions} session{check.result.sessions !== 1 ? 's' : ''} · {check.result.sets} sets
      {check.result.mobility_sets ? ` · ${check.result.mobility_sets} mobility` : ''}
    </p>
  ) : (
    <p className="program-check program-check--error">{check.error}</p>
  );

const move = <T,>(list: T[], from: number, to: number): T[] => {
  if (to < 0 || to >= list.length) return list;
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
};

const itemLabel = (item: BuilderItem) =>
  item.kind === 'block' ? `[${item.name}]` : item.kind === 'wave' ? item.exercise : item.text;

/** One day's add row: a block, a 5/3/1 lift, or any script line. */
const AddItem = ({ blockNames, onAdd }: { blockNames: string[]; onAdd: (item: BuilderItem) => void }) => {
  const { data: exercises } = useExercises();
  const [mode, setMode] = useState<'block' | 'wave' | 'line' | null>(null);
  const [block, setBlock] = useState('');
  const [exercise, setExercise] = useState('');
  const [tm, setTm] = useState('');
  const [line, setLine] = useState('');

  const close = () => {
    setMode(null);
    setBlock('');
    setExercise('');
    setTm('');
    setLine('');
  };

  if (mode === null) {
    return (
      <div className="builder-add">
        <Button size="sm" variant="secondary" onClick={() => setMode('block')}>
          <Plus style={{ width: '16px', height: '16px' }} />
          Block
        </Button>
        <Button size="sm" variant="secondary" onClick={() => setMode('wave')}>
          <Plus style={{ width: '16px', height: '16px' }} />
          5/3/1 lift
        </Button>
        <Button size="sm" variant="secondary" onClick={() => setMode('line')}>
          <Plus style={{ width: '16px', height: '16px' }} />
          Line
        </Button>
      </div>
    );
  }

  return (
    <div className="builder-add-form">
      {mode === 'block' && (
        <select
          className="input"
          aria-label="Block"
          value={block}
          onChange={(e) => setBlock(e.target.value)}
        >
          <option value="">Choose a block</option>
          {blockNames.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      )}
      {mode === 'wave' && (
        <>
          <ExerciseSearch
            exercises={exercises ?? []}
            value={exercise}
            onSelect={(ex) => setExercise(ex.name)}
            onClear={() => setExercise('')}
          />
          <Input
            type="number"
            inputMode="numeric"
            aria-label="Training max (lb)"
            placeholder="Training max, lb"
            value={tm}
            onChange={(e) => setTm(e.target.value)}
          />
        </>
      )}
      {mode === 'line' && (
        <Input
          aria-label="Script line"
          className="input--mono"
          placeholder="Pull Up / 3x8"
          value={line}
          onChange={(e) => setLine(e.target.value)}
        />
      )}
      <div className="flex" style={{ gap: 'var(--space-2)', justifyContent: 'flex-end' }}>
        <Button size="sm" variant="secondary" onClick={close}>
          Cancel
        </Button>
        <Button
          size="sm"
          disabled={
            (mode === 'block' && !block) ||
            (mode === 'wave' && (!exercise || !(Number(tm) > 0))) ||
            (mode === 'line' && !line.trim())
          }
          onClick={() => {
            if (mode === 'block') onAdd({ kind: 'block', name: block });
            if (mode === 'wave') onAdd({ kind: 'wave', exercise, tm: Number(tm) });
            if (mode === 'line') onAdd({ kind: 'line', text: line.trim() });
            close();
          }}
        >
          Add
        </Button>
      </div>
    </div>
  );
};

/** The builder: weeks, and days made of blocks, 5/3/1 lifts and lines. */
const Builder = ({ program, onDetach }: { program: Program; onDetach: () => void }) => {
  const { data: library } = useLibrary();
  const update = useUpdateProgram();
  const [model, setModel] = useState<BuilderModel>(program.builder!);
  const [savedModel, setSavedModel] = useState<BuilderModel>(program.builder!);
  const [showScript, setShowScript] = useState(false);
  const [confirmDetach, setConfirmDetach] = useState(false);

  const script = useMemo(() => buildScript(model), [model]);
  const check = useScriptCheck(script);
  const dirty = JSON.stringify(model) !== JSON.stringify(savedModel);
  const conflicts = conflictingMaxes(model);
  const blockNames = (library?.blocks ?? []).map((b) => b.name);

  const setDay = (index: number, change: (day: BuilderModel['days'][number]) => BuilderModel['days'][number]) =>
    setModel((m) => ({ ...m, days: m.days.map((d, i) => (i === index ? change(d) : d)) }));

  const save = async () => {
    await update.mutateAsync({ id: program.doc_id, changes: { script, builder: model } });
    setSavedModel(model);
  };

  return (
    <>
      <div className="builder-toolbar">
        <label className="builder-weeks">
          Weeks
          <Input
            type="number"
            inputMode="numeric"
            min={1}
            max={12}
            aria-label="Weeks"
            value={model.weeks}
            onChange={(e) => setModel((m) => ({ ...m, weeks: Math.min(12, Math.max(1, Number(e.target.value) || 1)) }))}
          />
        </label>
        <Button onClick={save} disabled={!dirty || update.isPending}>
          <Check style={{ width: '16px', height: '16px' }} />
          {dirty ? 'Save' : 'Saved'}
        </Button>
      </div>
      <CheckLine check={check} />
      {conflicts.length > 0 && (
        <p className="program-check program-check--error">
          {conflicts.join(', ')}: more than one training max - the first day's is used.
        </p>
      )}

      <div className="builder-days">
        {model.days.map((day, dayIndex) => (
          <Card key={dayIndex}>
            <CardContent>
              <div className="builder-day__head">
                <Input
                  aria-label={`Day ${dayIndex + 1} name`}
                  value={day.name}
                  onChange={(e) => setDay(dayIndex, (d) => ({ ...d, name: e.target.value }))}
                />
                <button type="button" className="action-btn" aria-label="Move day up"
                  onClick={() => setModel((m) => ({ ...m, days: move(m.days, dayIndex, dayIndex - 1) }))}>
                  <ArrowUp style={{ width: '16px', height: '16px' }} />
                </button>
                <button type="button" className="action-btn" aria-label="Move day down"
                  onClick={() => setModel((m) => ({ ...m, days: move(m.days, dayIndex, dayIndex + 1) }))}>
                  <ArrowDown style={{ width: '16px', height: '16px' }} />
                </button>
                <button type="button" className="action-btn action-btn--danger" aria-label="Remove day"
                  onClick={() => setModel((m) => ({ ...m, days: m.days.filter((_, i) => i !== dayIndex) }))}>
                  <Trash2 style={{ width: '16px', height: '16px' }} />
                </button>
              </div>

              <ol className="builder-items">
                {day.items.map((item, itemIndex) => (
                  <li key={itemIndex} className="builder-item">
                    <span className="builder-item__kind">
                      {item.kind === 'block' ? 'Block' : item.kind === 'wave' ? '5/3/1' : 'Line'}
                    </span>
                    <span className={`builder-item__label${item.kind === 'line' ? ' builder-item__label--mono' : ''}`}>
                      {itemLabel(item)}
                    </span>
                    {item.kind === 'wave' && (
                      <Input
                        type="number"
                        inputMode="numeric"
                        aria-label={`${item.exercise} training max`}
                        className="builder-item__tm"
                        value={item.tm}
                        onChange={(e) =>
                          setDay(dayIndex, (d) => ({
                            ...d,
                            items: d.items.map((it, i) =>
                              i === itemIndex && it.kind === 'wave' ? { ...it, tm: Number(e.target.value) || 0 } : it,
                            ),
                          }))
                        }
                      />
                    )}
                    <button type="button" className="action-btn" aria-label="Move up"
                      onClick={() => setDay(dayIndex, (d) => ({ ...d, items: move(d.items, itemIndex, itemIndex - 1) }))}>
                      <ArrowUp style={{ width: '16px', height: '16px' }} />
                    </button>
                    <button type="button" className="action-btn" aria-label="Move down"
                      onClick={() => setDay(dayIndex, (d) => ({ ...d, items: move(d.items, itemIndex, itemIndex + 1) }))}>
                      <ArrowDown style={{ width: '16px', height: '16px' }} />
                    </button>
                    <button type="button" className="action-btn action-btn--danger" aria-label="Remove"
                      onClick={() => setDay(dayIndex, (d) => ({ ...d, items: d.items.filter((_, i) => i !== itemIndex) }))}>
                      <X style={{ width: '16px', height: '16px' }} />
                    </button>
                  </li>
                ))}
              </ol>

              <AddItem
                blockNames={blockNames}
                onAdd={(item) => setDay(dayIndex, (d) => ({ ...d, items: [...d.items, item] }))}
              />
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="flex flex-wrap" style={{ gap: 'var(--space-2)', marginTop: 'var(--space-4)' }}>
        <Button
          variant="secondary"
          onClick={() =>
            setModel((m) => ({ ...m, days: [...m.days, { name: `Day ${m.days.length + 1}`, items: [] }] }))
          }
        >
          <Plus style={{ width: '16px', height: '16px' }} />
          Add day
        </Button>
        <Button variant="secondary" onClick={() => setShowScript(!showScript)}>
          <FileCode style={{ width: '16px', height: '16px' }} />
          {showScript ? 'Hide script' : 'Show script'}
        </Button>
        {confirmDetach ? (
          <>
            <Button
              variant="destructive"
              onClick={async () => {
                await update.mutateAsync({ id: program.doc_id, changes: { script } });
                onDetach();
              }}
            >
              Edit as script - leaves the builder
            </Button>
            <Button variant="secondary" onClick={() => setConfirmDetach(false)} aria-label="Stay in the builder">
              <X style={{ width: '16px', height: '16px' }} />
            </Button>
          </>
        ) : (
          <Button variant="secondary" onClick={() => setConfirmDetach(true)}>
            <Pencil style={{ width: '16px', height: '16px' }} />
            Edit as script
          </Button>
        )}
      </div>

      {showScript && (
        <Card style={{ marginTop: 'var(--space-4)' }}>
          <CardContent>
            <pre className="script-view">{script}</pre>
          </CardContent>
        </Card>
      )}
    </>
  );
};

/** A program written by hand (or detached from the builder). */
const ScriptProgram = ({ program }: { program: Program }) => {
  const update = useUpdateProgram();
  const [text, setText] = useState(program.script);
  const [saved, setSaved] = useState(program.script);
  const check = useScriptCheck(text);

  return (
    <>
      <div className="builder-toolbar">
        <CheckLine check={check} />
        <Button
          onClick={async () => {
            await update.mutateAsync({ id: program.doc_id, changes: { script: text } });
            setSaved(text);
          }}
          disabled={text === saved || update.isPending}
        >
          <Check style={{ width: '16px', height: '16px' }} />
          {text === saved ? 'Saved' : 'Save'}
        </Button>
      </div>
      <LiftoscriptEditor value={text} onChange={setText} error={check && !check.ok ? check.error : undefined} />
    </>
  );
};

/**
 * One program of yours (plan 0022): the builder when the builder wrote it,
 * the script editor otherwise. Generating happens on Upcoming - "Use in
 * Upcoming" opens its editor with this program.
 */
const ProgramEditor = () => {
  const { id } = useParams<{ id: string }>();
  const programId = Number(id);
  const navigate = useNavigate();
  const location = useLocation();
  const isNew = Boolean((location.state as { isNew?: boolean } | null)?.isNew);
  const { data: program, isError } = useProgram(programId);
  const update = useUpdateProgram();
  const remove = useDeleteProgram();

  const [editingName, setEditingName] = useState(isNew);
  const [draftName, setDraftName] = useState<string | null>(null);
  const [nameError, setNameError] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [detached, setDetached] = useState(false);

  useEffect(() => {
    if (!confirmDelete) return;
    const timer = setTimeout(() => setConfirmDelete(false), 3000);
    return () => clearTimeout(timer);
  }, [confirmDelete]);

  const saveName = async () => {
    if (!program) return;
    const name = (draftName ?? program.name).trim();
    if (!name) return setNameError('A program needs a name');
    if (name !== program.name) {
      try {
        await update.mutateAsync({ id: program.doc_id, changes: { name } });
      } catch (e: unknown) {
        const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        return setNameError(typeof detail === 'string' ? detail : 'Could not rename the program');
      }
    }
    setDraftName(null);
    setNameError('');
    setEditingName(false);
  };

  if (isError || Number.isNaN(programId)) {
    return (
      <>
        <Navigation />
        <div className="page">
          <div className="page__content page__content--narrow">
            <p style={{ color: 'var(--text-muted)' }}>This program does not exist.</p>
            <Button variant="secondary" onClick={() => navigate('/library')} style={{ marginTop: 'var(--space-4)' }}>
              Back to the library
            </Button>
          </div>
        </div>
      </>
    );
  }

  const inBuilder = program?.builder != null && !detached;

  return (
    <>
      <Navigation />
      <div className="page">
        <div className="page__content page__content--narrow">
          <div className="flex items-center animate-in" style={{ gap: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
            <Button variant="secondary" size="icon" className="icon-btn" onClick={() => navigate('/library')} aria-label="Back">
              <ArrowLeft style={{ width: '16px', height: '16px' }} />
            </Button>
            <div style={{ minWidth: 0, flex: 1 }}>
              {editingName ? (
                <span className="flex items-center" style={{ gap: 'var(--space-2)' }}>
                  <Input
                    aria-label="Program name"
                    autoFocus
                    value={draftName ?? program?.name ?? ''}
                    onFocus={(e) => isNew && e.currentTarget.select()}
                    onChange={(e) => {
                      setDraftName(e.target.value);
                      setNameError('');
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveName();
                      if (e.key === 'Escape') {
                        setDraftName(null);
                        setEditingName(false);
                      }
                    }}
                    style={{ fontSize: '18px', maxWidth: '360px' }}
                  />
                  <button type="button" className="action-btn" onClick={saveName} aria-label="Save name">
                    <Check style={{ width: '16px', height: '16px' }} />
                  </button>
                </span>
              ) : (
                <h1 className="page__title page__title--compact flex items-center" style={{ gap: 'var(--space-2)' }}>
                  {program?.name ?? ''}
                  {program && (
                    <button type="button" className="action-btn" onClick={() => setEditingName(true)} aria-label="Rename program">
                      <Pencil style={{ width: '16px', height: '16px' }} />
                    </button>
                  )}
                </h1>
              )}
              <p className="page__subtitle">
                {nameError ? (
                  <span style={{ color: 'var(--error)' }}>{nameError}</span>
                ) : inBuilder ? (
                  'Built with the builder'
                ) : (
                  'Script'
                )}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap" style={{ gap: 'var(--space-2)', marginBottom: 'var(--space-6)' }}>
            <Button
              variant="secondary"
              size="sm"
              disabled={!program}
              onClick={() => navigate('/upcoming', { state: { programId: program?.doc_id } })}
            >
              <Play style={{ width: '16px', height: '16px' }} />
              Use in Upcoming
            </Button>
            {confirmDelete ? (
              <Button
                variant="destructive"
                size="sm"
                onClick={async () => {
                  await remove.mutateAsync(programId);
                  navigate('/library');
                }}
              >
                <Check style={{ width: '16px', height: '16px' }} />
                Delete program
              </Button>
            ) : (
              <Button variant="secondary" size="sm" onClick={() => setConfirmDelete(true)}>
                <Trash2 style={{ width: '16px', height: '16px' }} />
                Delete
              </Button>
            )}
          </div>

          {program &&
            (inBuilder ? (
              <Builder key={program.doc_id} program={program} onDetach={() => setDetached(true)} />
            ) : (
              <ScriptProgram key={`${program.doc_id}-${detached}`} program={program} />
            ))}
        </div>
      </div>
    </>
  );
};

export default ProgramEditor;
