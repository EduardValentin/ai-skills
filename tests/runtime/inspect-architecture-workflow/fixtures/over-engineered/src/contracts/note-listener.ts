import type { NoteAdded } from "./note-events";

export interface NoteListener {
  onAdded(event: NoteAdded): void;
}
