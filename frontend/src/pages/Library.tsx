import { useNavigate } from 'react-router-dom';
import { ChevronRight, Plus } from 'lucide-react';
import Navigation from '@/components/Navigation';
import WorkoutSectionTabs from '@/components/WorkoutSectionTabs';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { useCreateWorkoutPreset } from '@/hooks/useWorkoutPresets';
import { useCreateProgram, useLibrary } from '@/hooks/useLibrary';
import { emptyBuilder, buildScript } from '@/lib/programBuilder';
import type { LibraryBlock, LibraryProgram } from '@/types/library';

/** "New program", numbered past any you already have. */
const unusedName = (base: string, taken: string[]) => {
  const lower = new Set(taken.map((n) => n.toLowerCase()));
  if (!lower.has(base.toLowerCase())) return base;
  let n = 2;
  while (lower.has(`${base} ${n}`.toLowerCase())) n++;
  return `${base} ${n}`;
};

const Row = ({
  title,
  meta,
  tag,
  onOpen,
}: {
  title: string;
  meta: string;
  tag?: string;
  onOpen: () => void;
}) => (
  <Card className="card-hover">
    <button type="button" className="library-row" onClick={onOpen}>
      <div style={{ minWidth: 0 }}>
        <div className="library-row__title">{title}</div>
        <p className="library-row__meta">{meta}</p>
      </div>
      <div className="flex items-center" style={{ gap: 'var(--space-3)', flexShrink: 0 }}>
        {tag && <span className="library-row__tag">{tag}</span>}
        <ChevronRight style={{ width: '16px', height: '16px', color: 'var(--text-muted)' }} />
      </div>
    </button>
  </Card>
);

/**
 * The library (plan 0022): blocks and programs, yours and built-in, all
 * script. A program is days and weeks - Upcoming generates the queue from one.
 * A block is part of a day, applied to one or pulled into a program with a
 * `[Block name]` line. Built-in ones are read-only; duplicate one to edit it.
 */
const Library = () => {
  const navigate = useNavigate();
  const { data: library, isLoading } = useLibrary();
  const createBlock = useCreateWorkoutPreset();
  const createProgram = useCreateProgram();

  const programs = library?.programs ?? [];
  const blocks = library?.blocks ?? [];

  const newProgram = async () => {
    const builder = emptyBuilder();
    const name = unusedName('New program', programs.filter((p) => p.source === 'mine').map((p) => p.name));
    const program = await createProgram.mutateAsync({ name, script: buildScript(builder), builder });
    navigate(`/library/programs/${program.doc_id}`, { state: { isNew: true } });
  };

  const newBlock = async () => {
    const block = await createBlock.mutateAsync(undefined);
    navigate(`/presets/${block.doc_id}`, { state: { isNew: true } });
  };

  const openProgram = (p: LibraryProgram) =>
    navigate(p.source === 'mine' ? `/library/programs/${p.id}` : `/library/programs/builtin/${p.key}`);
  const openBlock = (b: LibraryBlock) =>
    navigate(b.source === 'mine' ? `/presets/${b.id}` : `/library/blocks/${b.key}`);

  const sets = (n: number) => `${n} set${n !== 1 ? 's' : ''}`;

  return (
    <>
      <Navigation />
      <div className="page">
        <div className="page__content page__content--narrow">
          <div className="page__header animate-in">
            <h1 className="page__title">Library</h1>
            <p className="page__subtitle">Programs and the blocks they are built from</p>
          </div>

          <WorkoutSectionTabs />

          {isLoading ? (
            <div className="text-center" style={{ padding: 'var(--space-16) 0' }}>
              <div className="loading-spinner inline-block" />
            </div>
          ) : (
            <>
              <section className="library-section">
                <div className="library-section__head">
                  <div>
                    <h2 className="library-section__title">Programs</h2>
                    <p className="library-section__hint">Days and weeks. Generate one on Upcoming.</p>
                  </div>
                  <Button size="sm" onClick={newProgram} disabled={createProgram.isPending}>
                    <Plus style={{ width: '16px', height: '16px' }} />
                    New program
                  </Button>
                </div>
                <div className="library-list">
                  {programs.map((p) => (
                    <Row
                      key={`${p.source}-${p.id ?? p.key}`}
                      title={p.name}
                      meta={
                        p.source === 'mine'
                          ? p.built
                            ? 'Built with the builder'
                            : 'Script'
                          : (p.description ?? '')
                      }
                      tag={p.source === 'builtin' ? 'Built-in' : undefined}
                      onOpen={() => openProgram(p)}
                    />
                  ))}
                </div>
              </section>

              <section className="library-section">
                <div className="library-section__head">
                  <div>
                    <h2 className="library-section__title">Blocks</h2>
                    <p className="library-section__hint">
                      Part of a day. Apply one to a day, or add it to a program.
                    </p>
                  </div>
                  <Button size="sm" variant="secondary" onClick={newBlock} disabled={createBlock.isPending}>
                    <Plus style={{ width: '16px', height: '16px' }} />
                    New block
                  </Button>
                </div>
                <div className="library-list">
                  {blocks.map((b) => (
                    <Row
                      key={`${b.source}-${b.id ?? b.key}`}
                      title={b.name}
                      meta={sets(b.set_count)}
                      tag={b.source === 'builtin' ? 'Built-in' : undefined}
                      onOpen={() => openBlock(b)}
                    />
                  ))}
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    </>
  );
};

export default Library;
