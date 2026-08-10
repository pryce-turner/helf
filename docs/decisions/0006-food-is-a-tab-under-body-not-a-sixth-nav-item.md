# ADR-0006: Food is a tab under Body, not a sixth nav item

**Status:** Accepted
**Date:** 2026-08-09

## Context

Plan 0005 adds calorie tracking and, with it, a page. `Navigation.tsx` already
carries five items — Calendar, Progress, Body, Upcoming, Exercises — and the
same nav array drives both the desktop sidebar and the mobile bottom bar.

Five is already the ceiling on the mobile bar, and the repository knows it:
three separate commits have been navbar spacing fixes (`7aa5f44`, `accd72a`,
`cd5f32d`) plus one for double-tap (`c64434e`). Plan 0005 §4 calls a sixth item
a layout decision rather than an insertion, and declines to make it.

The candidates were:

1. **Six items.** Rejected: on a 375px viewport that is 62px per target, below
   the 44px touch minimum once the icon and label are inside it, and it reopens
   a bug class that has already cost four commits.
2. **An overflow "More" sheet.** The sheet itself occupies a slot, so this only
   helps at seven items or more, and it buys that by demoting two destinations
   instead of one. It also puts a daily-use action two taps deep.
3. **Demote Exercises, promote Food.** Coherent — Exercises is a catalog you
   edit occasionally, not a place you go daily — but it leaves Exercises with no
   route into it at all on mobile, which is a regression for a page that exists.
4. **Food as a tab alongside Body.** Chosen.

## Decision

**`/body-composition` and `/food` are two tabs of one section.** The nav keeps
five items; "Body" leads to the section, and a tab strip switches between
Composition and Food. Both tabs keep their own URL, so `/food` is bookmarkable
and installable as a home-screen shortcut — the fast path to logging a meal does
not cost a nav slot.

This is Plan 0005 §4's own suggestion, and the data model argues for it
independently. `v_daily_summary.kcal_target` is a Katch-McArdle RMR computed
from the *lean mass a DEXA scan measured* (Plan 0008 §8). Intake without that
target is a number with nothing to compare it to; the target without intake is
never used. They are one loop, and the tab strip is what says so.

## Consequences

- **The mobile bar stays at five.** No new spacing work, and the four fixes
  already paid for stay bought.
- **Food is two taps from cold, one from Body** — and zero from a home-screen
  shortcut to `/food`, which is how frequent logging is actually meant to
  happen.
- **The section is a real pattern, not a special case.** `SectionTabs` takes a
  list of routes, so the next thing that belongs beside an existing page —
  notes, most likely, which Plan 0005 also lands the API for — has somewhere to
  go without touching the nav.
- **`isActive` in `Navigation.tsx` needs to know about the alias.** "Body"
  highlights for `/food` as well as `/body-composition`, or the nav claims
  nothing is selected while the user is inside the section.
- **A seventh destination still has no home.** This defers the overflow
  question rather than answering it. That is deliberate: an overflow menu built
  before there is anything to overflow is a guess about which items are
  secondary, and this ADR only had evidence about one.
