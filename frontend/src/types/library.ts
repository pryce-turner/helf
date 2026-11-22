/**
 * The library (plan 0022): blocks and programs, yours and built-in, all
 * script. A block is part of a day (your blocks are the hand-built presets);
 * a program is days and weeks, and pulls blocks in with `[Block name]` lines.
 */
export interface LibraryBlock {
  source: "mine" | "builtin";
  name: string;
  set_count: number;
  /** Yours: the preset id. */
  id?: number;
  /** Built-in: the file key. */
  key?: string;
}

export interface LibraryProgram {
  source: "mine" | "builtin";
  name: string;
  id?: number;
  key?: string;
  /** Yours: the builder wrote it (and can reopen it). */
  built?: boolean;
  description?: string;
}

export interface Library {
  blocks: LibraryBlock[];
  programs: LibraryProgram[];
}

/** The program builder's model, saved beside the script it writes. */
export type BuilderItem =
  | { kind: "block"; name: string }
  /** A 5/3/1 main lift: the wave's week decides the sets, off a training max. */
  | { kind: "wave"; exercise: string; tm: number }
  /** Any one script line, e.g. "Pull Up / 3x8". */
  | { kind: "line"; text: string };

export interface BuilderDay {
  name: string;
  items: BuilderItem[];
}

export interface BuilderModel {
  weeks: number;
  days: BuilderDay[];
}

export interface Program {
  doc_id: number;
  name: string;
  script: string;
  builder: BuilderModel | null;
  created_at: string;
  updated_at: string;
}

export interface ScriptCheck {
  sets: number;
  sessions: number;
  mobility_sets: number;
}
