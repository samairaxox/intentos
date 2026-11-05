# Phase 2 evaluation results

Mocked Gemini; real LangGraph, CP-SAT, API, SQLite persistence and mock payment execution. No live model-quality, PostgreSQL concurrency or real-money claims. Timing excludes database fixture creation and includes local API flow; not production latency.

Generated (UTC): 2026-11-05T18:59:55.941217+00:00

| Metric | Observed value |
| --- | --- |
| scenario_count | 52 |
| passed | 52 |
| budget_compliance_rate | 1.0 |
| hard_constraint_satisfaction_rate | 1.0 |
| plan_checks | 64 |
| feasibility_counts | {'READY': 40, 'INFEASIBLE': 8, 'NEEDS_DETAILS': 4} |
| replanning_success_rate | 1.0 |
| payment_workflow_reliability | 1.0 |
| mean_optimized_utility | 104138.225 |
| mean_baseline_utility | 83944.875 |
| utility_comparisons | 40 |
| mean_execution_ms | 99.83028846153846 |
| p95_execution_ms | 155.49 |

## Baseline

The baseline independently selects the cheapest eligible available units for each required category, omits optional items, and reports infeasible when that cart exceeds budget. Both systems use the same integer utility function and original catalog snapshot. Utilities are synthetic heuristic units; they are not real-world savings or model accuracy.

| Scenario | Passed | Status | Utility / baseline | Time (ms) |
| --- | --- | --- | --- | --- |
| single-01 | True | READY | 12396 / 9693 | 125.358 |
| single-02 | True | READY | 20899 / 19075 | 106.116 |
| single-03 | True | READY | 22779 / 20704 | 69.745 |
| single-04 | True | READY | 24298 / 22689 | 56.187 |
| multi-01 | True | READY | 114581 / 91730 | 73.699 |
| multi-02 | True | READY | 136189 / 109280 | 79.474 |
| multi-03 | True | READY | 116186 / 92818 | 75.687 |
| multi-04 | True | READY | 116860 / 73227 | 74.691 |
| strict_budget-01 | True | READY | 85256 / 85256 | 65.837 |
| strict_budget-02 | True | READY | 87849 / 86895 | 77.224 |
| strict_budget-03 | True | READY | 92146 / 86727 | 104.099 |
| strict_budget-04 | True | READY | 95167 / 87789 | 78.535 |
| impossible_budget-01 | True | INFEASIBLE | - / - | 19.079 |
| impossible_budget-02 | True | INFEASIBLE | - / - | 155.49 |
| impossible_budget-03 | True | INFEASIBLE | - / - | 16.736 |
| impossible_budget-04 | True | INFEASIBLE | - / - | 17.77 |
| conflicting-01 | True | INFEASIBLE | - / - | 23.092 |
| conflicting-02 | True | INFEASIBLE | - / - | 30.176 |
| conflicting-03 | True | INFEASIBLE | - / - | 17.589 |
| conflicting-04 | True | INFEASIBLE | - / - | 19.416 |
| missing-01 | True | NEEDS_DETAILS | - / - | 13.475 |
| missing-02 | True | NEEDS_DETAILS | - / - | 11.898 |
| missing-03 | True | NEEDS_DETAILS | - / - | 12.279 |
| missing-04 | True | NEEDS_DETAILS | - / - | 11.596 |
| unavailable-01 | True | READY | 114581 / 91730 | 167.217 |
| unavailable-02 | True | READY | 115362 / 90956 | 146.892 |
| unavailable-03 | True | READY | 116186 / 92818 | 129.651 |
| unavailable-04 | True | READY | 116860 / 91912 | 154.535 |
| price_increase-01 | True | READY | 114581 / 91730 | 154.97 |
| price_increase-02 | True | READY | 115362 / 90956 | 151.51 |
| price_increase-03 | True | READY | 116186 / 92818 | 149.543 |
| price_increase-04 | True | READY | 116860 / 91912 | 175.627 |
| price_decrease-01 | True | READY | 114581 / 91730 | 137.033 |
| price_decrease-02 | True | READY | 115362 / 90956 | 154.082 |
| price_decrease-03 | True | READY | 116186 / 92818 | 155.37 |
| price_decrease-04 | True | READY | 116860 / 91912 | 144.054 |
| seller_unavailable-01 | True | READY | 114581 / 91730 | 146.832 |
| seller_unavailable-02 | True | READY | 115362 / 90956 | 151.524 |
| seller_unavailable-03 | True | READY | 116186 / 92818 | 137.923 |
| seller_unavailable-04 | True | READY | 116860 / 91912 | 156.642 |
| budget_change-01 | True | READY | 114581 / 91730 | 147.705 |
| budget_change-02 | True | READY | 115362 / 90956 | 138.919 |
| budget_change-03 | True | READY | 116186 / 92818 | 127.226 |
| budget_change-04 | True | READY | 116860 / 91912 | 136.516 |
| preference_change-01 | True | READY | 114581 / 91730 | 138.092 |
| preference_change-02 | True | READY | 115362 / 90956 | 144.886 |
| preference_change-03 | True | READY | 116186 / 92818 | 135.301 |
| preference_change-04 | True | READY | 116860 / 91912 | 146.318 |
| payment_failure-01 | True | READY | 114581 / 91730 | 78.001 |
| payment_failure-02 | True | READY | 115362 / 90956 | 97.879 |
| payment_failure-03 | True | READY | 116186 / 92818 | 78.491 |
| payment_failure-04 | True | READY | 116860 / 91912 | 73.188 |
