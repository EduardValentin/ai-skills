import { FileInvoiceStore } from "../storage/file-invoice-store";
import { IssueInvoiceUseCase } from "../billing/issue-invoice-use-case";
import { storageFolder } from "./config";

export const main = () => new IssueInvoiceUseCase(new FileInvoiceStore());
export const folder = storageFolder;
