import type { NoteValidator } from "./note-validator";
import type { Note } from "./note";

export class DefaultNoteValidator implements NoteValidator {
  validate(note: Note): boolean {
    return note.title.text.length > 0;
  }
}
