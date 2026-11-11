import type { LoanStore } from "./loan-store";

export class OverdueFee {
  constructor(private readonly store: LoanStore) {}
}
