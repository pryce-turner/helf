# 0014 — Several mobility sessions, addressed by label

**Status**: Implemented 2026-08-20 · migration `b6f31a90c4de`

Supersedes plan 0012 §2's "one rolling routine, not a queue".

## 1. Why one was not enough

0012 was right that a mobility program is a rolling routine rather than a
generated block, and wrong that there is only ever one of them. Rehabbing a low
back and a shoulder at the same time means two prescriptions alive at once,
adjusted on different schedules from different feedback. A single pending
session forces them into one list — seven movements maximum, so they cannot
both fit — or makes writing either one destroy the other, since
`write_next_mobility_session` replaced everything pending.

The instruction that followed from it is the tell: *"if a session is already
pending, stop there"*. A loop whose write step is guarded by "don't" is a loop
that cannot be used twice in a week.

## 2. The items needed no schema

`upcoming_workouts.session` has always distinguished sessions — the lifting
planner is using 7 through 12 right now — and mobility pinned itself to a
constant `MOBILITY_SESSION = 1`. Several mobility sessions are several values
of a column that was already there.

What had nowhere to live was **per-session metadata**. There was exactly one
rationale, in a `note` of kind `mobility_plan`, and no name at all: two pending
sessions would have been indistinguishable on the page and unaddressable by the
agent. So `mobility_plan` became a table, one row per pending session, holding
`label`, `rationale` and the `session` its items share.

It is **not audited**, matching `upcoming_workouts`: 0007's audited set is
history, and a session that has not been run is not history. Transfer is the
moment it becomes history, and that still writes a `note`.

## 3. The label is the key

`write_next_mobility_session(label, items, rationale)`. A new label adds a
session; an existing one replaces that session and cannot touch the others.

Chosen over a numeric session id because the agent would have had to read the
pending list to learn the id, and an id is easy to get wrong in a way that
silently overwrites the wrong programme. A label is what the user already says
— "update the shoulder one" — and it makes the destructive case legible: you
can see from the call which session it replaces.

Chosen over always-appending because a mistaken prescription then needs two
steps to correct, and the tab accumulates near-duplicates that the user has to
tell apart.

Labels name **what the session is for**, not what is in it, because that is
what the user is choosing between on the page.

## 4. Reading a named day

`read_latest_mobility_session(date=…)`. With no argument it still derives the
most recent day carrying flagged sets. With a date it reads that day — which is
how a session gets built from one the user points at.

**A named date with no flagged sets returns `found: false`**, rather than
falling back to everything logged that day. The flag is the only thing that
says a set was mobility work (0013), and programming from a day's lifting sets
because they happened to be there is worse than reporting nothing. The hint
says to flag the day instead.

## 5. The page

`/mobility` lists every pending session, each a card with its label, reasoning,
movements, and its **own** Copy-to-calendar and Discard. Card state is local:
shared state would open every calendar at once and arm every discard from one
tap.

Transferring one leaves the others pending, which is the behaviour the whole
change exists for.

## 6. Verification

`pytest` — 390 passed, including that two labels are two independent sessions,
that transferring one leaves the other, that discarding one leaves the other,
that rewriting a label revises only its own session, and that a label is
required. `npm test` — 54 passed, including a page rendering two sessions where
transferring the second names session 2. eslint, tsc and build clean.

Live database at `b6f31a90c4de`: the single pending routine carried across as
label `Mobility` with its 15 rows and rationale intact.

## 7. Not done

**No per-session schedule or ordering.** Sessions are listed by `session`
number, which is creation order, and nothing records how often one should be
run or which is due. If that becomes a real question the answer is probably a
field on `mobility_plan`, not a second mechanism — but "which do I feel like
running" is currently answered by looking at the two cards.
