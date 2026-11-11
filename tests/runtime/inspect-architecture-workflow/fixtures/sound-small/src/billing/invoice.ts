import { Money } from "./money";

export class Invoice {
  constructor(readonly total: Money) {}
}
