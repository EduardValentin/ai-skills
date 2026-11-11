import { LoanUseCase } from "../lending/loan-use-case";
import { SqlLoanStore } from "../storage/sql-loan-store";

export class LoanController {}
export const builtSqlLoanStore = new SqlLoanStore();
export const isSqlLoanStore = (value: unknown) => value instanceof SqlLoanStore;
