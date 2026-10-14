import type { Employee } from "../domain/employee";

export const memoryPayrollRepository = {
  async save(employee: Employee) {},
  find(id: string) {
    return undefined;
  },
};
