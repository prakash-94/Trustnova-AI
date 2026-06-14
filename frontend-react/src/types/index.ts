export * from './banking';

export interface CustomerSummary {
  customer_id: string;
  name: string;
  email?: string;
}
