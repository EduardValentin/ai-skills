import type { InvoiceStore } from "../billing/invoice-store";
import { Invoice } from "../billing/invoice";

export class FileInvoiceStore implements InvoiceStore {
  save(invoice: Invoice): void {}
}
