import { Combination } from "@/lib/multi";
import { money } from "@/lib/api";
const colors = ["#24694d", "#579479", "#84ad78", "#b3c39a", "#d3c59a"];
export default function BudgetAllocation({
  combination,
  budget,
}: {
  combination: Combination;
  budget: number;
}) {
  return (
    <section className="allocation">
      <div className="allocation-header">
        <div>
          <p className="eyebrow">BUDGET ALLOCATION</p>
          <h2>
            {money(combination.total_cost)} <small>of {money(budget)}</small>
          </h2>
        </div>
        <div>
          <strong>{money(combination.remaining_budget)}</strong>
          <p>remaining</p>
        </div>
      </div>
      <div
        className="allocation-bar"
        role="img"
        aria-label={`Category allocation, ${money(combination.total_cost)} spent out of ${money(budget)}`}
      >
        {Object.entries(combination.category_spending).map(
          ([category, amount], i) => (
            <span
              key={category}
              title={`${category}: ${money(amount)}`}
              style={{
                width: `${(amount / budget) * 100}%`,
                background: colors[i % colors.length],
              }}
            />
          ),
        )}
      </div>
      <div className="allocation-legend">
        {Object.entries(combination.category_spending).map(
          ([category, amount], i) => (
            <span key={category}>
              <i style={{ background: colors[i % colors.length] }} />
              {category}: {money(amount)}
            </span>
          ),
        )}
      </div>
      <p className="demo-note">
        Utility: {combination.utility_score.toLocaleString()} heuristic units ·
        Solver: {combination.solver_status || "User-edited cart"}. Scores and
        prices are demonstration data.
      </p>
    </section>
  );
}
