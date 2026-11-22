# 0022 — The library: blocks and programs, all script

**Status**: Implemented 2026-11-22 · `47920bce115b`

Presets (0020) and programs turned out to be one idea at two sizes: a preset
is part of a day, a program is days and weeks, and both become planned sets
through the same parser. This unifies them without flattening the difference.

## 1. Two shapes, one format

| | Block | Program |
|---|---|---|
| Size | part of a day, no `## Day` headers | days, often weeks |
| Varies by week | no | yes (`%`, `lp()`, the builder's waves) |
| Used by | Apply to a day; `[Name]` in a program | Generate (replaces the queue) |
| Edited in | the day editor, set by set | the builder, or the script |

**Built-in is not a third kind — it is who wrote it.** Built-in blocks
(`app/presets/blocks/`) and programs (`app/presets/*.liftoscript`) stay files in
the repo, read-only in the library, with Duplicate to edit. Seeding them into
the database would turn every later change to one into a merge against the
user's copy.

## 2. Script gains includes and comments

- `[Block name]` on its own line is replaced by the block's lines **before**
  anything else is parsed. Resolution: built-in names, then yours (built-in
  names are reserved, so one name never means two things). A block may include
  blocks, never itself (the cycle is named), and has no `## Day` headers.
  Errors carry their origin: "Line 3 of block 'Press core'".
- `"quoted comment"` in a spec lands on its sets' `comment` (after `AMRAP`).
  It is taken out first, so its text is never read as tokens, and commas or
  slashes inside it do not split the line.
- Pound weights keep their decimals (17.5lb); only kilogram conversions round.

## 3. Your blocks stay rows

The day editor is the better tool for a block, so `workout_preset` stays the
storage and `preset_to_script` is the view: one line per run of identical sets
(`2x6 2.5lb`), comments quoted. One loss: a tile with no rep count is written
`1x1`.

## 4. Your programs get a table

`workout_program`: name (unique), script, and `builder` — the builder's JSON
model when the builder wrote the script. The builder writes script and never
reads one, so a script-only update is a hand edit and detaches it. Upcoming's
Program dropdown lists built-in and saved programs; Save as program keeps what
is in the editor. The last-generated-program document (0021 §4a's sibling)
stays as the editor's default.

## 5. The builder

Weeks, and days of three item kinds: a block, a **5/3/1 wave lift** (exercise +
training max; week *n* takes wave `(n-1) % 4`, so it repeats), and any script
line. Training maxes go to the top as `1RM` lines; two maxes for one lift are
flagged and the first wins. It shows the server's parse of its output live.

## 6. Built-ins rebuilt from blocks

5/3/1 Core Stability's days are now `[Day warm-up]`, `[Day core]`, the wave,
accessories, `[Day cool-down]` — twelve built-in blocks. Same 372 sets, 16
sessions, 124 mobility; the chops-and-lifts sets now carry their side as
comments.

## 7. Not done

- Applying a **built-in** block straight to a day: duplicate it first.
- Wave kinds beyond 5/3/1 (a fixed line covers static work).
- Renaming a block does not rewrite the programs that include it; the next
  generate names the missing block.
