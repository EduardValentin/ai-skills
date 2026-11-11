import type { Note } from "./note";

export interface NoteValidator {
  validate(note: Note): boolean;
}
