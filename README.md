# Helf — Health & Fitness Tracker

A Progressive Web App for tracking training, body composition and intake. FastAPI
+ React + SQLite, single-user, self-hosted.

Eight years of workout history, a smart scale publishing over MQTT, quarterly
DEXA scans pulled from an API, and a calorie target computed from measured lean
mass rather than a formula fed by bodyweight.

---

## Features

### Training

- **Calendar** — month view with per-day workout counts and a current streak.
- **Session logging** — weight, reps, distance, time and comments per set.
  Drag to reorder within a day; mark sets complete; move or copy a whole day to
  another date.
- **Exercise catalog** — organised by category, with usage counts and last-used
  dates. Seedable with 16 presets across 6 categories.
- **Progression charts** — estimated 1RM over time, `(0.033 × reps × weight) +
  weight`, with configurable moving averages and projections from planned work.
- **Liftoscript** — a small language for defining programs, with Wendler 5/3/1
  and StrongLifts 5×5 built in. Generate multiple sessions from one script and
  transfer them into history with one click.

### Body composition

- **Three instruments, kept apart** — a bioimpedance scale over MQTT
  (near-daily), and DEXA scans from BodySpec and DexaFit (quarterly). They
  measure the same quantities and disagree by design; on 2026-03-10 the scale
  read 6.15 percentage points of body fat above the DEXA scan taken hours
  later. Charts plot the scale as a line and DEXA as unjoined points, and no
  statistic ever averages or differences across them.
- **BodySpec import** — paste an access token to pull scans. The token is used
  for one request and stored nowhere.
- **Trends and stats** — configurable periods, with the instrument each delta
  describes named on screen.

### Intake

- **Food log** — a catalog with macros per serving, logged with servings, meal
  and time. Correcting a food's macros corrects every past entry, because a
  serving's numbers are derived rather than stored.
- **A measured calorie target** — `kcal_target` is the last DEXA scan's
  Katch-McArdle resting rate × 1.4, carried forward from the most recent scan
  on or before each day. It is blank before your first scan; there is no
  default, because a target no measurement supports is worse than none.
- **Honest totals** — unknown macros count as zero and the page says how many
  entries are responsible, rather than showing a confident low number.

### Supplements

- **Stacks** — named groups you take together: morning is omega, vitamin D and
  CholestOff; evening is magnesium and omega. One tap logs the group.
- Supplements are stored as foods, so whey protein's calories land in the day's
  intake while a vitamin's absence of macros doesn't distort it.
- **Adherence is derived, not marked** — a stack counts as taken when every one
  of its items appears in that day's log, so it is true whether you tapped the
  button or entered the items by hand.

### Agent access

- **MCP server** — `backend/app/mcp/qs_mcp.py` exposes the database to any MCP
  client over stdio. **Read-only by default**; write tools are not registered
  unless `QS_MCP_MODE=read-write`.
- **Audit log** — every edit and deletion is recorded by database triggers,
  including who made it, in a table that cannot be updated or deleted.

### PWA

Offline support via Workbox, installable on mobile and desktop, auto-update
prompt, dark-first design with an orange accent, desktop sidebar and mobile
bottom bar.

---

## Quick start

```bash
cp .env.example .env          # set HELF_DATA_PATH
docker-compose up -d          # http://localhost:30171
```

Local development — backend on 8000, frontend on 5173 proxying `/api`:

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --port 8000

cd frontend && npm install && npm run dev
```

API docs are at `/docs` (Swagger) and `/redoc`.

---

## Architecture

```
┌──────────────────────────────────────────────┐
│  PWA — React 19, TanStack Query, Workbox     │
└───────────────────────┬──────────────────────┘
                        │ HTTP
┌───────────────────────▼──────────────────────┐
│  FastAPI                                     │
│    api/           routes, no business logic  │
│    services/      MQTT, Liftoscript, DEXA    │
│    repositories/  SQLAlchemy queries         │
│    models/        Pydantic — the HTTP shape  │
│    db/models.py   SQLAlchemy — the tables    │
└──────┬─────────────────────────┬─────────────┘
       │                         │
┌──────▼──────┐           ┌──────▼──────┐
│ MQTT broker │           │  helf.db    │
│ (the scale) │           │  SQLite/WAL │
└─────────────┘           └──────┬──────┘
                                 │ same file, second process
                          ┌──────▼──────────────┐
                          │  MCP server         │
                          │  read-only by       │
                          │  default, stdio     │
                          └─────────────────────┘
```

Two processes share one SQLite file rather than one calling the other — the app
uses SQLAlchemy, the agent uses raw SQL, and the privilege boundary is the
connection rather than a tool name. WAL and `busy_timeout` are what make that
safe; 110 concurrent operations across both processes produce no lock errors.

**Pydantic models and SQLAlchemy tables are deliberately separate.** The
body-composition response has fifteen fields and no table behind it — it is
assembled from a view over a tall `metric` store. That separation is why
dropping the old wide table changed nothing for the frontend.

### The data model in one paragraph

Training is flat: a `workouts` row is one logged set, and a session is the rows
sharing a date. Everything measured is tall: an `observation` is one act of
measuring (a time and an instrument) carrying `metric` rows named from a fixed
vocabulary in `metric_def`, so adding a quantity is a row rather than a
migration. Intake is `food` plus `food_log`, with supplements as foods and
`stack` grouping them. Anything without a settled shape lands in `note` (prose)
or `document` (raw payloads) and gets promoted later. `audit_log` records
mutations and is append-only.

**Units live in names.** Pounds are canonical for body mass, so there is no
unit column anywhere — `body_weight_lb` and `bone_mass_kg` say what they are.

Full reasoning is in [`docs/`](docs/README.md): decisions in
`docs/decisions/`, the implementation history in `docs/plans/`.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HELF_DATA_PATH` | — | Host path for the data volume mount |
| `DATA_DIR` | `/app/data` | Container path for the SQLite database |
| `MQTT_BROKER_HOST` | `host.docker.internal` | MQTT broker hostname |
| `MQTT_BROKER_PORT` | `1883` | MQTT broker port |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `PRODUCTION` | `true` | Production mode flag |
| `QS_DB_PATH` | `settings.db_path` | Database path for the MCP server |
| `QS_MCP_MODE` | `read-only` | `read-write` registers the agent's write tools |

### MQTT

Subscribes to `openScaleSync/measurements/last` and `.../all`. Weights arrive in
kilograms and are converted to pounds on the way in; percentages, indices and
bone mass are not converted. Check with `curl localhost:30171/api/mqtt/status`.

---

## Liftoscript

```
// Squat 1RM: 315lb
// Bench Press 1RM: 225lb

## Week 1 Day 1
Squat / 3x5 65%
Bench Press / 3x5 65%
Pull Ups / 3x8 bodyweight
```

- `## Day Name` starts a session; `Exercise / sets x reps weight` defines work.
- Weights: `135lb`, `60kg`, `65%` of 1RM, or `bodyweight`. kg converts and
  rounds to the nearest 5 lb.
- `progress: lp(5lb)` for linear progression; `// Exercise SW: 135lb` sets its
  starting weight.
- `5+` marks an AMRAP top set. It is **program notation only** — the parser
  resolves it to an integer plus an "AMRAP" comment, and no `+` ever reaches
  the database (ADR-0005).

---

## Testing

```bash
cd backend && pytest          # 302 tests
ruff check .
.venv/bin/alembic check       # ORM vs migrations drift

cd frontend && npm run lint && npm run build
```

Test fixtures build the database **by running the real migrations** against a
temporary file — not `create_all()`, and not in memory. The read path queries
views and `metric_def` carries a seeded vocabulary, neither of which exists in
ORM metadata, so `create_all()` produces a database the app cannot run against.

---

## Database and migrations

SQLite at `${DATA_DIR}/helf.db`, WAL enabled, schema managed by Alembic.

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```

**WAL means `cp` is not a consistent copy.** Back up with:

```bash
sqlite3 data/helf.db ".backup 'data/helf.db.bak'"
```

The schema is deliberately not written out in prose anywhere — it would go
stale and then be believed. `backend/app/db/models.py` carries a docstring per
table, the plan that created each table explains why it is shaped that way, and
`sqlite3 data/helf.db .schema` is authoritative.

### Migrating from v1.x

```bash
cd backend && python migrations/tinydb_to_sqlite.py
```

Converts a legacy TinyDB JSON export, including kilogram weights into the
canonical pounds.

---

## Documentation

| Where | What |
|---|---|
| [`docs/README.md`](docs/README.md) | Index, and where the schema is actually described |
| [`docs/decisions/`](docs/decisions/) | ADRs — settled decisions and why |
| [`docs/plans/README.md`](docs/plans/README.md) | Status of every implementation plan |
| [`AGENTS.md`](AGENTS.md) | The system as it is today, for coding agents |
| [`backend/README.md`](backend/README.md), [`frontend/README.md`](frontend/README.md) | Per-package detail |

## Roadmap

- [x] FastAPI backend, React PWA, Docker deployment
- [x] Liftoscript program language, drag-and-drop reordering
- [x] Tall metric model, Alembic migrations, WAL
- [x] BodySpec DEXA import and a measured calorie target
- [x] Food logging and supplement stacks
- [x] MCP server (read-only) and an append-only audit log
- [ ] Enable agent write tools — built and tested, deliberately off
- [ ] Notes UI — the API exists, nothing renders it
- [ ] Blood work import — no data source yet
- [ ] E2E tests (Playwright)

## License

[MIT](LICENSE).

---

**Version** 2.0.0 · FastAPI + React 19 + SQLite
