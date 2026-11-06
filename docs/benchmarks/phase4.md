# Phase 4 measured demo benchmark

IntentOS synthetic demo catalog; fixed fixture clock 2026-01-15T12:00:00Z; no live observations

| Budget | Profile | Categories | Immediate INR | Lowest INR | Optimized INR | Runtime ms | +10% replan |
|---:|---|---:|---:|---:|---:|---:|---|
| 75000 | cost_focused | 2 | 64977.50 | 56577.50 | 56577.50 | 27.07 | True |
| 75000 | cost_focused | 5 | 64763.75 | 59663.75 | 59663.75 | 31.276 | True |
| 75000 | balanced | 2 | 64977.50 | 56577.50 | 64977.50 | 32.302 | True |
| 75000 | balanced | 5 | 64763.75 | 59663.75 | 64763.75 | 51.353 | True |
| 75000 | risk_averse | 2 | 64977.50 | 56577.50 | 63777.50 | 36.496 | True |
| 75000 | risk_averse | 5 | 64763.75 | 59663.75 | 64463.75 | 48.577 | True |
| 100000 | cost_focused | 2 | 76077.50 | 56577.50 | 56577.50 | 23.839 | True |
| 100000 | cost_focused | 5 | 88163.75 | 59663.75 | 59663.75 | 35.082 | True |
| 100000 | balanced | 2 | 76077.50 | 56577.50 | 76077.50 | 29.636 | True |
| 100000 | balanced | 5 | 88163.75 | 59663.75 | 88163.75 | 45.574 | True |
| 100000 | risk_averse | 2 | 76077.50 | 56577.50 | 76077.50 | 62.765 | True |
| 100000 | risk_averse | 5 | 88163.75 | 59663.75 | 88264.00 | 99.903 | True |
| 125000 | cost_focused | 2 | 76077.50 | 56577.50 | 56577.50 | 58.422 | True |
| 125000 | cost_focused | 5 | 88163.75 | 59663.75 | 59663.75 | 83.45 | True |
| 125000 | balanced | 2 | 76077.50 | 56577.50 | 76077.50 | 68.606 | True |
| 125000 | balanced | 5 | 88163.75 | 59663.75 | 88163.75 | 108.567 | True |
| 125000 | risk_averse | 2 | 76077.50 | 56577.50 | 76077.50 | 73.807 | True |
| 125000 | risk_averse | 5 | 88163.75 | 59663.75 | 88264.00 | 103.285 | True |

Measured summary: `{"cases": 18, "strategy_comparisons": 54, "feasible_comparisons": 54, "hard_constraint_violations": 0, "consistent_repeats": 18, "price_increase_replans_feasible": 18, "mean_comparison_runtime_ms": 56.667}`

- Costs are simulated, not real-world savings.
- Runtime covers three strategy solves and assessment, and varies by machine.
- Immediate baseline maximizes existing utility; lowest-price baseline minimizes landed cost under identical hard constraints.
- Consistency uses a fixed catalog and clock. Replan feasibility is measured for a hypothetical 10% laptop base-price increase.
