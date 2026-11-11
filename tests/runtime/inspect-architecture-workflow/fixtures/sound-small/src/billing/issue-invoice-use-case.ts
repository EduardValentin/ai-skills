import { Invoice } from "./invoice";
import { LineItem } from "./line-item";
import type { InvoiceStore } from "./invoice-store";

export class IssueInvoiceUseCase {
  constructor(private readonly store: InvoiceStore) {}
  issue(items: LineItem[]) {
    this.store.save(new Invoice(items[0].price));
  }
}
