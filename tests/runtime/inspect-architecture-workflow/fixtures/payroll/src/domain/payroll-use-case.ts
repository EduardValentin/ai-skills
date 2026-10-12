import { Employee } from "./employee";
import { Clock } from "./clock";
import { PayrollRepository } from "./payroll-repository";

export class PayrollUseCase {
  constructor(private readonly repository: PayrollRepository, private readonly clock: Clock) {}

  run(employee: Employee): void {}
}
