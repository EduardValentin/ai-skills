# over-engineered fixture

A small invented notes application that does one thing, add a note, behind needless structure: an interface for
every class (each with one implementer and one consumer), a facade layer that only forwards, a mapper boundary whose
two sides always change together, and two interface-only components (`contracts`, `hooks`) that nothing implements or
uses. The command must conclude that nothing here needs more structure.

`arch check` raises only the `unused-abstractions` rows for `contracts` and `hooks`, and no row whose correction adds a
port, an interface, a layer, or a component. The judgment findings below are not checked by the command; a reviewer
is expected to raise them, and a person verifies that by hand:

| Judgment | Target |
|---|---|
| `abstraction-without-reason` (R8) | `src/domain/note-validator.ts#NoteValidator`, `src/facade/note-facade.ts#NoteFacade` |
| `boundary-defers-nothing` (R25) | `src/domain/note-mapper.ts#NoteMapper`, component `facade` |
