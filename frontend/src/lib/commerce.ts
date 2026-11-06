import { MultiIntent } from "./multi";
export interface CommerceIntent extends MultiIntent {
  allowed_merchants?: string[];
  blocked_merchants?: string[];
}
export interface Offer {
  id: string;
  product_id: string;
  merchant_id: string;
  merchant_name: string;
  base_price: string;
  shipping: string;
  fees: string;
  currency: string;
  stock: number;
  source_type: string;
  verification_status: string;
  retrieved_at: string;
  expires_at: string | null;
}
export interface Pricing {
  base_price: string;
  confirmed_discount: string;
  shipping: string;
  fees: string;
  estimated_taxes: string;
  final_price: string;
  taxes_supported: boolean;
  potential_discounts: { label: string; amount: string }[];
  cost_scope: string;
}
export interface OfferView {
  offer: Offer;
  product: {
    id: string;
    name: string;
    category: string;
    brand: string;
    model: string;
    specifications: Record<string, unknown>;
  };
  pricing: Pricing;
  freshness: {
    label: string;
    fresh: boolean;
    checkout_eligible: boolean;
    reason: string;
    valid_until: string;
  };
}
export interface CommerceLine extends OfferView {
  quantity: number;
  line_total: string;
  reason: string;
}
export interface CommerceCombination {
  items: CommerceLine[];
  total: string;
  remaining_budget: string;
  cost_breakdown: Record<string, string>;
  merchant_totals: Record<string, string>;
  merchant_allocation: {
    merchant_id: string;
    amount: string;
    share_percent: string;
  }[];
  utility_score: number;
  solver_status: string;
  explanation: string;
}
export interface CommercePlan {
  id: string;
  session_id: string;
  parent_id: string | null;
  version: number;
  status: string;
  intent: CommerceIntent;
  result: {
    combinations?: CommerceCombination[];
    offers?: OfferView[];
    missing_information?: string[];
  };
  workflow: { completed?: string[]; ai_used?: boolean };
  changes: string[];
  purchase_ids: string[];
}
export interface CommerceSession {
  id: string;
  version: number;
  intent: CommerceIntent;
  conversation: { role: string; text: string }[];
  latest_plan_id: string;
  plans: { id: string; version: number; status: string }[];
}
export interface SessionResult {
  session: CommerceSession;
  plan: CommercePlan;
}
export type Simulation =
  | "success"
  | "failure"
  | "timeout_captured"
  | "timeout_unknown"
  | "checkout_failure";
export interface MerchantOrder {
  id: string;
  merchant_id: string;
  merchant_name: string;
  amount: string;
  status: string;
  items: CommerceLine[];
  attempts: {
    id: string;
    status: string;
    attempt_number: number;
    retry_after: string | null;
  }[];
}
export interface CommercePurchase {
  id: string;
  plan_id: string;
  status: string;
  amount: string;
  snapshot: CommerceCombination;
  approved: boolean;
  suborders: MerchantOrder[];
  execution_key: string | null;
  execution_modes: Record<string, Simulation>;
  captured_total: string;
  refunded_total: string;
  warning: string;
  workflow: { action_required?: string; completed?: string[] };
}
export interface CommerceTrace {
  id: string;
  workflow_id: string;
  node: string;
  status: string;
  details: Record<string, string | number | null>;
  created_at: string;
}
// Format backend Decimal strings without monetary arithmetic or float conversion.
export function exactMoney(value: string) {
  const [whole, fraction = "00"] = value.split(".");
  const prefix = whole.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return (
    "₹" +
    (prefix ? prefix + "," : "") +
    whole.slice(-3) +
    "." +
    fraction.padEnd(2, "0")
  );
}
