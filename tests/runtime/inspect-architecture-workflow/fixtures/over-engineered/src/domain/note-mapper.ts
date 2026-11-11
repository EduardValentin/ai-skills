import type { Note } from "./note";

export interface NoteMapper {
  toRow(note: Note): string;
}
