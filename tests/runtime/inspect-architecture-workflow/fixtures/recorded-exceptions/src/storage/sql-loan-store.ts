import type { LoanStore } from "../lending/loan-store";

export class SqlLoanStore implements LoanStore {
  count(): number {
    return 0;
  }
}
