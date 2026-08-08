# Helf Frontend

React 19 + TypeScript Progressive Web App for the Helf health and fitness tracker.

## Tech Stack

| Technology | Version | Purpose |
|---|---|---|
| React | 19.2+ | UI framework |
| TypeScript | 5.9+ | Type safety |
| Vite | 7.2+ | Build tool & dev server |
| Tailwind CSS | 4.1+ | Utility-first styling |
| TanStack Query | 5.x | Server state management |
| React Router | 7.x | Client-side routing |
| Recharts | 3.6+ | Data visualization |
| dnd-kit | 6.3+ | Drag-and-drop reordering |
| shadcn/ui | - | Radix UI + Tailwind components |
| Axios | 1.13+ | HTTP client |
| date-fns | 4.1+ | Date formatting |
| Lucide React | 0.562+ | Icons |
| vite-plugin-pwa | 1.2+ | PWA / service worker |

## Development

```bash
npm install
npm run dev       # Dev server on http://localhost:5173
npm run build     # TypeScript check + production build
npm run lint      # ESLint
npm run preview   # Preview production build
```

The Vite dev server proxies `/api` requests to `http://localhost:8000` (the FastAPI backend).

## Project Structure

```
src/
├── App.tsx                    # Router, QueryClient, layout
├── main.tsx                   # Entry point, service worker registration
├── index.css                  # Design system (CSS custom properties)
├── components/
│   ├── Navigation.tsx         # Sidebar (desktop) / bottom bar (mobile)
│   ├── LiftoscriptEditor.tsx  # Script editor for workout programs
│   ├── PresetSelector.tsx     # Dropdown for built-in workout presets
│   ├── PWA/
│   │   └── InstallPrompt.tsx  # "Add to Home Screen" prompt
│   └── ui/                    # shadcn/ui primitives
│       ├── button.tsx
│       ├── card.tsx
│       ├── input.tsx
│       ├── label.tsx
│       ├── select.tsx
│       └── calendar.tsx
├── hooks/
│   ├── useWorkouts.ts         # Workout CRUD, calendar, reorder, move/copy
│   ├── useExercises.ts        # Exercise & category CRUD, seed
│   ├── useProgression.ts      # 1RM progression data
│   ├── useBodyComposition.ts  # Body comp measurements & trends
│   ├── useUpcoming.ts         # Upcoming workouts, Liftoscript, presets
│   └── usePWA.ts              # Online status, install prompt
├── lib/
│   └── api.ts                 # Axios instance + all API functions
├── pages/
│   ├── Calendar.tsx           # Month view with workout indicators + streak
│   ├── WorkoutSession.tsx     # Day view: log exercises, drag-reorder, complete
│   ├── Progression.tsx        # 1RM charts with moving average + projections
│   ├── Upcoming.tsx           # Session planner, Liftoscript editor, presets
│   ├── BodyComposition.tsx    # Trends, stats, manual entry
│   └── Exercises.tsx          # Exercise catalog by category
└── types/
    ├── workout.ts             # Workout, WorkoutCreate, CalendarResponse
    ├── exercise.ts            # Exercise, Category, SeedExercisesResponse
    ├── progression.ts         # ProgressionDataPoint, ProgressionResponse
    ├── upcoming.ts            # UpcomingWorkout, Liftoscript types, PresetInfo
    └── bodyComposition.ts     # BodyComposition, Stats, Trend
```

## Routes

| Path | Page | Description |
|---|---|---|
| `/` | Calendar | Month view with workout count dots |
| `/day/:date` | WorkoutSession | Log exercises for a specific date |
| `/progression` | Progression | Main lifts (Bench/Squat/Deadlift) charts |
| `/progression/:exercise` | Progression | Single exercise 1RM chart |
| `/upcoming` | Upcoming | Plan future workouts with Liftoscript |
| `/body-composition` | BodyComposition | Weight/body fat trends and stats |
| `/exercises` | Exercises | Browse and manage exercise catalog |

## API Client

All API calls are centralized in `src/lib/api.ts` using Axios. The client groups are:

- **`workoutsApi`** - CRUD, calendar, reorder, move/copy dates, toggle complete
- **`exercisesApi`** - CRUD, recent, seed presets
- **`categoriesApi`** - CRUD, list exercises by category
- **`progressionApi`** - Exercise progression data, main lifts, exercise list
- **`upcomingApi`** - CRUD, bulk create, session transfer, Liftoscript generation, presets
- **`bodyCompositionApi`** - CRUD, latest, stats, trends

## State Management

**TanStack Query (React Query v5)** handles all server state:

- **5-minute stale time** by default (no refetch on window focus)
- **Optimistic updates** on create/update/delete mutations
- **Cache invalidation** on mutation success
- **Query keys** follow `["resource", ...params]` convention

No client-side state management library (Redux, Zustand, etc.) is used. Local UI state is managed with React's `useState` and `useRef`.

## Design System

Defined in `src/index.css` via CSS custom properties:

### Colors
- **Background**: `--bg-base` (#09090b), `--bg-primary`, `--bg-secondary`, `--bg-tertiary`
- **Text**: `--text-primary` (#fafafa), `--text-secondary`, `--text-muted`
- **Accent**: `--accent` (#f97316 orange)
- **Semantic**: `--success` (#22c55e), `--warning` (#eab308), `--error` (#ef4444), `--info` (#3b82f6)
- **Charts**: `--chart-1` through `--chart-5`

### Typography
- **Display**: Clash Display (headings)
- **Body**: Satoshi (UI text)
- **Mono**: JetBrains Mono (numbers, stats)

### Tokens
- Border radius: `--radius-sm` (6px) to `--radius-full` (9999px)
- Shadows: `--shadow-sm` to `--shadow-lg`
- Durations: `--duration-fast` (100ms), `--duration-normal` (150ms), `--duration-slow` (250ms)

## PWA Configuration

Configured in `vite.config.ts`:

- **Register type**: `autoUpdate` with user prompt
- **Manifest**: App name, icons (192x192, 512x512, maskable), theme color
- **Workbox caching**:
  - Google Fonts: CacheFirst (1 year TTL)
  - API requests (`/api/`): NetworkFirst (5 min cache, 10s network timeout)
- **Offline**: Service worker registered in `main.tsx`, online status tracked in `usePWA`

## Key Patterns

### Adding a new page
1. Create component in `src/pages/NewPage.tsx`
2. Add React Query hooks in `src/hooks/useNewData.ts`
3. Add API functions in `src/lib/api.ts`
4. Add types in `src/types/newData.ts`
5. Register route in `App.tsx`
6. Add nav link in `components/Navigation.tsx`

### Adding a new UI component
1. Use `npx shadcn@latest add <component>` or create manually in `src/components/ui/`
2. Follow existing patterns: use `cn()` utility, CVA variants, Radix primitives

### Optimistic updates
Mutations in hooks follow this pattern:
```typescript
onMutate: async (newData) => {
  await queryClient.cancelQueries({ queryKey: ['resource'] });
  const previous = queryClient.getQueryData(['resource']);
  queryClient.setQueryData(['resource'], (old) => /* optimistic update */);
  return { previous };
},
onError: (err, vars, context) => {
  queryClient.setQueryData(['resource'], context?.previous);
},
onSettled: () => {
  queryClient.invalidateQueries({ queryKey: ['resource'] });
},
```
