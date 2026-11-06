import { CommerceIntent, CommerceCombination } from "./commerce";
export type FinancialGoal = Omit<CommerceIntent, "total_budget"> & {
  total_budget: string | null;
  mandatory_reserve: string;
  category_limits: Record<string, string>;
  risk_strategy: "cost_focused" | "balanced" | "risk_averse";
  patience_days: number;
  deadline: string | null;
  opportunity_cost_per_day: string;
  target_total: string | null;
  history_mode: "recorded" | "synthetic_demo";
};
export interface Risk {
  index: string;
  offer_weighted_index: string;
  budget_utilization_percent: string;
  largest_seller_percent: string;
  method: string;
  delivery: string;
  offers: Record<
    string,
    {
      index: string;
      provenance: string;
      freshness: string;
      stock_scarcity: string;
      volatility: string;
      volatility_unknown: boolean;
      method: string;
    }
  >;
}
export interface Strategy {
  code: string;
  status: string;
  executable: boolean;
  plan: CommerceCombination | null;
  risk?: Risk | null;
  explanation?: string;
  deferred_categories?: string[];
}
export interface PriceHistory {
  offer_id: string;
  mode: string;
  count: number;
  evidence: string;
  minimum?: string;
  maximum?: string;
  average?: string;
  volatility_percent?: string;
  current_price?: string;
  current_minus_average?: string;
  points: {
    price: string;
    at: string;
    source: string;
    verification: string;
    kind: string;
  }[];
  chart_points?: { x: string; y: string }[];
}
export interface FinancialResult {
  status: string;
  hypothetical: boolean;
  recommended: string | null;
  reserve?: {
    available: string;
    mandatory_reserve: string;
    spendable: string;
    encumbered?: string;
    new_purchase_capacity?: string;
    category_limits: Record<string, string>;
  };
  strategies: Strategy[];
  explanation: string;
  assumptions: string[];
  change_triggers: string[];
  wait?: {
    status: string;
    days: number;
    explanation: string;
    target_total?: string;
    opportunity_cost?: string;
    conditional_net_difference?: string;
    stock_at_risk?: boolean;
  };
  runtime_ms?: number;
  missing_information?: string[];
}
export interface FinancialScenario {
  id: string;
  parameters: unknown;
  result: FinancialResult;
}
export interface FinancialDecision {
  id: string;
  session_id: string;
  parent_id: string | null;
  status: string;
  goal: FinancialGoal | null;
  latest_decision_id: string;
  result: FinancialResult;
  histories: Record<string, PriceHistory>;
  workflow: { completed: string[] };
  scenarios: FinancialScenario[];
  purchase_ids: string[];
}
