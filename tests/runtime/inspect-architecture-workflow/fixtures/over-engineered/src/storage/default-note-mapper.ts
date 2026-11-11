import type { NoteMapper } from "../domain/note-mapper";
import { Note } from "../domain/note";

export class DefaultNoteMapper implements NoteMapper {
  toRow(note: Note): string {
    return note.title.text;
  }
}
