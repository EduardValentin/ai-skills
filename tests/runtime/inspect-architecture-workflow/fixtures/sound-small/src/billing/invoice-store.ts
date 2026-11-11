import type { Invoice } from "./invoice";

export interface InvoiceStore {
  save(invoice: Invoice): void;
}
