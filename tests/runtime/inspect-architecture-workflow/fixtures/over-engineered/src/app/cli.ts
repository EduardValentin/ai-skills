import type { NoteFacade } from "../facade/note-facade";

export const runCli = (facade: NoteFacade) => facade.add("first note");
