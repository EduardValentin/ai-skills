import express from "express";
import { PayrollUseCase } from "../domain/payroll-use-case";
import { PgPayrollRepository } from "../adapters/pg-payroll-repository";
import { SystemClock } from "../adapters/system-clock";

export function payrollController(): express.Router {
  const router = express.Router();
  return router;
}
