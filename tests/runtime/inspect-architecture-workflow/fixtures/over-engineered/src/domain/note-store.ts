import type { Note } from "./note";

export interface NoteStore {
  save(row: string, note: Note): void;
}
