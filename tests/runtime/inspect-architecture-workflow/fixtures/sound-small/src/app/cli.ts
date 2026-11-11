import { IssueInvoiceUseCase } from "../billing/issue-invoice-use-case";

export const runCli = (useCase: IssueInvoiceUseCase) => useCase.issue([]);
