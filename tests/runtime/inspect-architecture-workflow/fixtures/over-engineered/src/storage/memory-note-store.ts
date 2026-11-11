import type { NoteStore } from "../domain/note-store";
import { Note } from "../domain/note";

export class MemoryNoteStore implements NoteStore {
  save(row: string, note: Note): void {}
}
