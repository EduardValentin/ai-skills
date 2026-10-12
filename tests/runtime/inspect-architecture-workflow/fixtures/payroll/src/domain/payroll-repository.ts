export interface PayrollRepository {
  save(employee: unknown): Promise<void>;
}
