import type { PayrollRepository } from "../domain/payroll-repository";
import { Employee } from "../domain/employee";
import pg from "pg";

export class PgPayrollRepository implements PayrollRepository {
  constructor(private readonly pool: pg.Pool) {}

  async save(employee: Employee): Promise<void> {}
}
