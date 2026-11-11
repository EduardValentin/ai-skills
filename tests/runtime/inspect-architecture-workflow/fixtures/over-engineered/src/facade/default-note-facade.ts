import type { NoteFacade } from "./note-facade";
import { AddNoteUseCase } from "../domain/add-note-use-case";
import { Note } from "../domain/note";
import { NoteTitle } from "../domain/note-title";

export class DefaultNoteFacade implements NoteFacade {
  constructor(private readonly useCase: AddNoteUseCase) {}
  add(title: string): void {
    this.useCase.add(new Note(new NoteTitle(title)));
  }
}
