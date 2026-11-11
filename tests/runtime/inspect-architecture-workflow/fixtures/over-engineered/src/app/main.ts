import { MemoryNoteStore } from "../storage/memory-note-store";
import { DefaultNoteMapper } from "../storage/default-note-mapper";
import { DefaultNoteValidator } from "../domain/default-note-validator";
import { AddNoteUseCase } from "../domain/add-note-use-case";
import { DefaultNoteFacade } from "../facade/default-note-facade";

const useCase = new AddNoteUseCase(new DefaultNoteValidator(), new DefaultNoteMapper(), new MemoryNoteStore());
export const main = () => new DefaultNoteFacade(useCase);
