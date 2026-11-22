import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Copy, Play } from 'lucide-react';
import Navigation from '@/components/Navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { upcomingApi } from '@/lib/api';
import { useBuiltinBlock, useCreateProgram, useDuplicateBuiltinBlock, useLibrary } from '@/hooks/useLibrary';

/**
 * A built-in block or program, read-only (plan 0022): its script, and a copy
 * of your own to edit. Built-ins are files in the repo, so they can be
 * updated with the app without a merge against your edits.
 */
const LibraryItemView = ({ kind }: { kind: 'block' | 'program' }) => {
  const { key } = useParams<{ key: string }>();
  const navigate = useNavigate();
  const { data: library } = useLibrary();
  const block = useBuiltinBlock(kind === 'block' ? key : undefined);
  const program = useQuery({
    queryKey: ['presets', key],
    queryFn: async () => (await upcomingApi.getPreset(key!)).data,
    enabled: kind === 'program' && !!key,
  });
  const duplicateBlock = useDuplicateBuiltinBlock();
  const createProgram = useCreateProgram();

  const name = kind === 'block' ? block.data?.name : program.data?.display_name;
  const script = kind === 'block' ? block.data?.script : program.data?.script;
  const description =
    kind === 'program' ? library?.programs.find((p) => p.key === key)?.description : undefined;
  const isError = kind === 'block' ? block.isError : program.isError;

  const duplicate = async () => {
    if (kind === 'block') {
      const made = await duplicateBlock.mutateAsync(key!);
      navigate(`/presets/${made.doc_id}`);
      return;
    }
    const taken = new Set((library?.programs ?? []).map((p) => p.name.toLowerCase()));
    let copyName = `${name} (mine)`;
    for (let n = 2; taken.has(copyName.toLowerCase()); n++) copyName = `${name} (mine) ${n}`;
    const made = await createProgram.mutateAsync({ name: copyName, script: script ?? '' });
    navigate(`/library/programs/${made.doc_id}`);
  };

  return (
    <>
      <Navigation />
      <div className="page">
        <div className="page__content page__content--narrow">
          <div className="flex items-center animate-in" style={{ gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}>
            <Button variant="secondary" size="icon" className="icon-btn" onClick={() => navigate('/library')} aria-label="Back">
              <ArrowLeft style={{ width: '16px', height: '16px' }} />
            </Button>
            <div style={{ minWidth: 0 }}>
              <h1 className="page__title page__title--compact">{name ?? (isError ? 'Not found' : '')}</h1>
              <p className="page__subtitle">Built-in {kind} · read-only</p>
            </div>
          </div>

          {description && <p className="library-description">{description}</p>}

          <div className="flex flex-wrap" style={{ gap: 'var(--space-2)', marginBottom: 'var(--space-6)' }}>
            <Button onClick={duplicate} disabled={!script || duplicateBlock.isPending || createProgram.isPending}>
              <Copy style={{ width: '16px', height: '16px' }} />
              Duplicate to edit
            </Button>
            {kind === 'program' && (
              <Button
                variant="secondary"
                disabled={!script}
                onClick={() => navigate('/upcoming', { state: { programKey: key } })}
              >
                <Play style={{ width: '16px', height: '16px' }} />
                Use in Upcoming
              </Button>
            )}
          </div>

          <Card>
            <CardContent>
              <pre className="script-view">{script ?? ''}</pre>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
};

export default LibraryItemView;
