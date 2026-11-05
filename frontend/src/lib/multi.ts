export interface Rule {
  field: string;
  operator: "eq" | "min" | "max";
  value: string | number | boolean;
}
export type Category =
  "laptop" | "monitor" | "keyboard" | "mouse" | "headphones";
export interface ItemRequirement {
  category: Category;
  quantity: number;
  required: boolean;
  priority: number;
  hard_constraints: Rule[];
  soft_preferences: Rule[];
}
export interface MultiIntent {
  total_budget: number | null;
  currency: string;
  items: ItemRequirement[];
  priorities: string[];
  weights: Record<string, number>;
  spending_preference: string;
  use_case: string;
  missing_information: string[];
}
export interface MultiProduct {
  id: string;
  category: Category;
  name: string;
  brand: string;
  model: string;
  price: number;
  specifications: Record<string, string | number | boolean>;
  seller: string;
  source_type: string;
  timestamp: string;
}
export interface PlanLine {
  product: MultiProduct;
  quantity: number;
  unit_price: number;
  line_total: number;
  utility: number;
  reason: string;
}
export interface Combination {
  items: PlanLine[];
  total_cost: number;
  remaining_budget: number;
  utility_score: number;
  category_spending: Record<string, number>;
  tradeoffs: string[];
  omitted_optional: string[];
  solver_status?: string;
}
export interface Plan {
  order_ids: string[];
  id: string;
  parent_id: string | null;
  revision: number;
  status: string;
  intent: MultiIntent;
  result: {
    combinations: Combination[];
    candidates: Record<string, MultiProduct[]>;
    missing_information: string[];
    revised_plan_id?: string | null;
  };
  workflow: { steps: string[]; awaiting_selection: boolean };
  changes: string[];
}
export interface Cart {
  alternative_index?: number;
  id: string;
  plan_id: string;
  version: number;
  status: string;
  snapshot: Combination;
}
export interface BundleOrder {
  id: string;
  cart_id: string;
  amount: number;
  status: string;
  items: {
    quantity: number;
    unit_price: number;
    seller: string;
    snapshot: MultiProduct;
  }[];
  payment?: { id: string; status: string; amount: number } | null;
}
export const categories: Category[] = [
  "laptop",
  "monitor",
  "keyboard",
  "mouse",
  "headphones",
];
