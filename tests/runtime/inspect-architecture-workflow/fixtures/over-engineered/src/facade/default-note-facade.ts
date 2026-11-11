import type { NoteFacade } from "./note-facade";
import { AddNoteUseCase } from "../domain/add-note-use-case";

export class DefaultNoteFacade implements NoteFacade {
  constructor(private readonly useCase: AddNoteUseCase) {}
  add(title: string): void {}
}
