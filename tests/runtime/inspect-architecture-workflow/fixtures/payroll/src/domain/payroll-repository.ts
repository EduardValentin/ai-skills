import type { Employee } from "./employee";

export interface PayrollRepository {
  save(employee: Employee): Promise<void>;
}
