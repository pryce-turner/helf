import { ScrollText } from 'lucide-react';
import Navigation from '@/components/Navigation';
import WorkoutSectionTabs from '@/components/WorkoutSectionTabs';
import { Card, CardContent } from '@/components/ui/card';

/**
 * Presets, a tab of its own under Workouts beside Upcoming.
 *
 * A placeholder for now: presets are built by hand. The program editor that
 * generates the queue from a Liftoscript template stays on Upcoming.
 */
const Presets = () => (
  <>
    <Navigation />
    <div className="page">
      <div className="page__content page__content--narrow">
        <div className="page__header animate-in">
          <h1 className="page__title">Preset</h1>
          <p className="page__subtitle">Workouts you build by hand and reuse</p>
        </div>

        <WorkoutSectionTabs />

        <Card style={{ border: '2px dashed var(--border)', background: 'transparent' }}>
          <CardContent className="empty-state">
            <div className="empty-state__icon">
              <ScrollText style={{ width: '40px', height: '40px', color: 'var(--text-muted)' }} />
            </div>
            <h3 className="empty-state__title">No presets yet</h3>
            <p className="empty-state__text">Presets you build will show up here.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  </>
);

export default Presets;
