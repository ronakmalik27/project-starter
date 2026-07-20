# Decision framework

Not every decision needs a formal record. This doc sets the line between a
decision that is recorded inline and a decision that gets an Architecture
Decision Record (ADR), plus how an ADR moves through its lifecycle.

## When to write an ADR

Write an ADR when a decision meets any of these:

- **Expensive to reverse.** Changing course later would mean a significant
  rewrite, a data migration, or a breaking change to something external
  consumers depend on.
- **Affects multiple modules.** The decision sets a convention or a
  constraint that more than one part of the system has to live with.
- **A future reader will ask "why did we do it this way."** If you can
  picture someone six months from now being confused by the choice without
  context, write the context down now, while it is cheap to write.

If a decision meets none of these, it does not need an ADR.

## Two-way doors vs one-way doors

Frame every non-trivial decision by how reversible it is:

- **Two-way door (reversible).** You can make the call, ship it, and change
  your mind later at low cost. Make these fast and cheap. Do not slow the
  team down with process for a decision that costs little to undo.
- **One-way door (hard to reverse).** Once made, undoing the decision is
  expensive or impossible. These deserve more scrutiny before the call is
  made: an ADR, a second opinion, and time to think, not a snap decision
  under deadline pressure.

Most decisions are two-way doors. Treating every decision as a one-way door
makes the team slow; treating a one-way door as a two-way door is how
expensive mistakes happen.

## ADR lifecycle

```
proposed -> accepted -> superseded
```

- **Proposed.** The ADR is drafted: the context, the options considered, the
  decision, and the consequences (including the downsides accepted).
- **Accepted.** The decision is made and the ADR reflects the option chosen.
  From this point, the ADR is the record of why the system is built the way
  it is.
- **Superseded.** A later decision replaces this one. The old ADR is never
  deleted or rewritten: it stays as a historical record, and it is updated
  only to add a link to the ADR that replaces it. This preserves the
  reasoning trail: a reader can see not just what the system does today, but
  what it used to do and why it changed.

## Where ADRs live

The ADR template lives at `docs/adr/0000-template.md`. New ADRs are numbered
sequentially and stored alongside it in `docs/adr/`.

## Small, reversible decisions

A two-way-door decision is recorded inline: a short note in the relevant doc
explaining the choice, or a sentence in the pull request description. It
does not need its own ADR file, a review cycle, or a lifecycle state. The
bar for "just write it down somewhere sensible" is much lower than the bar
for "write a formal ADR," and most day-to-day decisions should clear only
the lower bar.
