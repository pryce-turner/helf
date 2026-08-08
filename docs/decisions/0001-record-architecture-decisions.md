# ADR-0001: Record architecture decisions

**Status:** Accepted
**Date:** 2026-08-07

## Context

Helf has already been through one full rewrite (NiceGUI monolith → FastAPI +
React) and is now facing a second round of structural change: a new schema
shape, a unit migration, and an LLM-facing MCP surface. The reasoning behind the
first rewrite survives only as prose in `CLAUDE.md` and as commit messages.

The decisions now on the table are the kind that get silently re-litigated six
months later — "why is everything in kg?", "why isn't the agent just hitting the
REST API?" — because the *reasoning* wasn't written down next to the code, only
the outcome.

The design doc that prompted this round came from a chat conversation and lived
in `~/Downloads` until it was deliberately hunted down. That is the failure mode
this directory exists to prevent.

## Decision

Record architecturally significant decisions as ADRs in `docs/decisions/`, using
a lightweight Context / Decision / Consequences format.

A decision is "architecturally significant" if reversing it later would require
touching multiple layers, migrating data, or breaking an external contract.
Routine choices (library versions, file layout, naming) do not need an ADR.

ADRs are **immutable once Accepted**. A decision that changes gets a new ADR that
marks the old one `Superseded by ADR-NNNN`. The record of having believed
something is itself worth keeping.

## Consequences

- Reasoning outlives the conversation, the branch, and the contributor.
- Small ongoing cost: a new ADR per significant decision.
- Risk of ceremony. Mitigation: ADRs are short, and only the significant
  decisions get one. If it takes more than twenty minutes to write, it's
  probably a design doc instead.
- Requires discipline to write the ADR *at* decision time. One written
  retroactively is a rationalization, not a record.
