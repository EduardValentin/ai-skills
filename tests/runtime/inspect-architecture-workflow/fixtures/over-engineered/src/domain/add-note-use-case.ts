import { Note } from "./note";
import type { NoteValidator } from "./note-validator";
import type { NoteMapper } from "./note-mapper";
import type { NoteStore } from "./note-store";

export class AddNoteUseCase {
  constructor(
    private readonly validator: NoteValidator,
    private readonly mapper: NoteMapper,
    private readonly store: NoteStore,
  ) {}
  add(note: Note) {
    if (this.validator.validate(note)) this.store.save(this.mapper.toRow(note), note);
  }
}
