export * from './banking';

export interface CustomerSummary {
  customer_id: string;
  name: string;
  email?: string;
  credit_score?: number;
  risk_level?: string;
  account_type?: string;
  since?: string;
}
