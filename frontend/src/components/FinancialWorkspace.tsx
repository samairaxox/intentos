"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { categories } from "@/lib/multi";
import { CommercePurchase, Simulation, exactMoney } from "@/lib/commerce";
import {
  FinancialGoal,
  FinancialDecision,
  FinancialResult,
  FinancialScenario,
  Strategy,
  PriceHistory,
} from "@/lib/finance";
import MerchantPayments from "./MerchantPayments";

const base = "/api/v1/finance";
const commerce = "/api/v1/commerce";
const initial: FinancialGoal = {
  total_budget: "100000.00",
  mandatory_reserve: "10000.00",
  currency: "INR",
  items: categories.map((category) => ({
    category,
    quantity: 1,
    required: true,
    priority: category === "laptop" ? 5 : 3,
    hard_constraints:
      category === "laptop"
        ? [{ field: "ram_gb", operator: "min", value: 16 }]
        : [],
    soft_preferences: [],
  })),
  category_limits: {},
  risk_strategy: "balanced",
  patience_days: 14,
  deadline: null,
  opportunity_cost_per_day: "0.00",
  target_total: null,
  history_mode: "recorded",
  priorities: ["Coding performance", "Value"],
  weights: {
    performance: 5,
    quality: 3,
    portability: 1,
    battery: 1,
    value: 4,
    preferences: 3,
    cost_savings: 2,
  },
  spending_preference: "balanced",
  use_case: "Coding setup",
  missing_information: [],
};

function PlanCard({
  strategy,
  busy,
  onSelect,
}: {
  strategy: Strategy;
  busy: boolean;
  onSelect?: (code: string) => void;
}) {
  return (
    <article className="finance-card">
      <div className="finance-card-top">
        <h3>{strategy.code.replaceAll("_", " ")}</h3>
        <span className="tag">{strategy.status}</span>
      </div>
      {strategy.plan ? (
        <>
          <strong className="finance-price">
            {exactMoney(strategy.plan.total)}
          </strong>
          <p className="finance-muted">
            Unallocated: {exactMoney(strategy.plan.remaining_budget)} of
            spendable budget
          </p>
          <ul className="finance-lines">
            {strategy.plan.items.map((line) => (
              <li key={line.offer.id}>
                <div>
                  <strong>{line.product.name}</strong>
                  <small>
                    {line.quantity} × {line.offer.merchant_name} ·{" "}
                    {line.freshness.label}
                  </small>
                </div>
                <span>{exactMoney(line.line_total)}</span>
              </li>
            ))}
          </ul>
          <p>{strategy.explanation || strategy.plan.explanation}</p>
          {strategy.risk && (
            <details>
              <summary>
                Risk index {strategy.risk.index}/100 · inspect method
              </summary>
              <p>{strategy.risk.method}</p>
              <dl className="finance-facts">
                <dt>Offer risk</dt>
                <dd>{strategy.risk.offer_weighted_index}</dd>
                <dt>Budget utilization</dt>
                <dd>{strategy.risk.budget_utilization_percent}%</dd>
                <dt>Largest seller share</dt>
                <dd>{strategy.risk.largest_seller_percent}%</dd>
              </dl>
              <p>{strategy.risk.delivery}</p>
              {Object.entries(strategy.risk.offers).map(([id, r]) => (
                <p key={id}>
                  <strong>{id}</strong>
                  <br />
                  Provenance {r.provenance}; quote age {r.freshness}; scarcity{" "}
                  {r.stock_scarcity}; volatility {r.volatility}
                  {r.volatility_unknown ? " (unknown-history penalty)" : ""}.
                  <br />
                  {r.method}
                </p>
              ))}
            </details>
          )}
          {onSelect && (
            <button
              className="primary"
              disabled={busy || !strategy.executable}
              onClick={() => onSelect(strategy.code)}
            >
              Prepare {strategy.code.replaceAll("_", " ")} checkout
            </button>
          )}
        </>
      ) : (
        <p>No feasible basket under the current constraints.</p>
      )}
    </article>
  );
}

function HistoryChart({ history }: { history: PriceHistory }) {
  return (
    <div className="finance-history">
      <span className="tag">
        {history.mode === "synthetic_demo"
          ? "SYNTHETIC DEVELOPMENT DATA"
          : "Recorded quotes · source shown below"}
      </span>
      <p>
        {history.count} observations · {history.evidence.replaceAll("_", " ")}
      </p>
      {history.chart_points && history.count > 1 ? (
        <svg
          viewBox="0 0 300 110"
          role="img"
          aria-label={`Observed landed unit prices, minimum ${history.minimum}, maximum ${history.maximum}. No forecast.`}
        >
          <line x1="10" y1="95" x2="290" y2="95" stroke="#cbd5cc" />
          <polyline
            fill="none"
            stroke="#276d4e"
            strokeWidth="2"
            points={history.chart_points.map((p) => `${p.x},${p.y}`).join(" ")}
          />
          {history.chart_points.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r="2" fill="#276d4e">
              <title>
                {history.points[i].at}: {exactMoney(history.points[i].price)} ·{" "}
                {history.points[i].source}
              </title>
            </circle>
          ))}
        </svg>
      ) : (
        <p className="finance-empty">
          More observations are needed for a history chart.
        </p>
      )}
      {history.minimum && (
        <dl className="finance-facts">
          <dt>Observed minimum / maximum</dt>
          <dd>
            {exactMoney(history.minimum)} / {exactMoney(history.maximum!)}
          </dd>
          <dt>Observed mean</dt>
          <dd>{exactMoney(history.average!)}</dd>
          <dt>Population volatility (CV)</dt>
          <dd>{history.volatility_percent}%</dd>
          <dt>Current landed price</dt>
          <dd>{exactMoney(history.current_price || "0.00")}</dd>
          <dt>Current minus observed mean</dt>
          <dd>{history.current_minus_average} INR</dd>
        </dl>
      )}
      <p className="finance-muted">
        Past observations do not predict future discounts. Synthetic samples
        never mix with recorded quotes.
      </p>
      <details>
        <summary>Observation sources and timestamps</summary>
        <div className="finance-observations">
          {history.points.map((p, i) => (
            <p key={i}>
              {new Date(p.at).toLocaleString()} · {exactMoney(p.price)} ·{" "}
              {p.source} · {p.verification}
            </p>
          ))}
        </div>
      </details>
    </div>
  );
}

export default function FinancialWorkspace() {
  const [goal, setGoal] = useState<FinancialGoal>(initial),
    [decision, setDecision] = useState<FinancialDecision | null>(null);
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [restoreId, setRestoreId] = useState("");
  const [purchase, setPurchase] = useState<CommercePurchase | null>(null),
    [modes, setModes] = useState<Record<string, Simulation>>({}),
    [executionKey, setExecutionKey] = useState("");
  const [text, setText] = useState(
    "I have INR 100000 for a coding setup: laptop, monitor, keyboard, mouse and headphones. Keep INR 10000 untouched. I can wait 14 days.",
  );
  const [natural, setNatural] = useState(false),
    [selectedHistory, setSelectedHistory] = useState("");
  const [scenarioType, setScenarioType] = useState("price"),
    [scenarioCategory, setScenarioCategory] = useState("laptop"),
    [scenarioValue, setScenarioValue] = useState("10"),
    [scenario, setScenario] = useState<FinancialScenario | null>(null);
  useEffect(() => {
    setRestoreId(localStorage.getItem("intentos-financial-decision") || "");
  }, []);
  function accept(d: FinancialDecision) {
    setDecision(d);
    if (d.goal) setGoal(d.goal);
    setRestoreId(d.id);
    localStorage.setItem("intentos-financial-decision", d.id);
    setScenario(null);
    setSelectedHistory(
      d.result.strategies.find((s) => s.code === "optimized")?.plan?.items[0]
        ?.offer.id ||
        Object.keys(d.histories)[0] ||
        "",
    );
  }
  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
      if (
        err instanceof ApiError &&
        err.detail &&
        typeof err.detail === "object"
      ) {
        const detail = err.detail as {
          revised_decision_id?: string;
          decision_id?: string;
        };
        if (detail.decision_id) setRestoreId(detail.decision_id);
        if (detail.revised_decision_id) {
          try {
            accept(
              await api<FinancialDecision>(
                `${base}/decisions/${detail.revised_decision_id}`,
              ),
            );
            if (purchase)
              setPurchase(
                await api<CommercePurchase>(
                  `${commerce}/purchases/${purchase.id}`,
                ),
              );
            setNotice(
              "Terms changed. Review the revised decision and prepare a new checkout.",
            );
          } catch {
            setNotice("Reload the saved decision to inspect current terms.");
          }
        }
      }
    } finally {
      setBusy("");
    }
  }
  async function restore(d: FinancialDecision) {
    accept(d);
    const id = d.purchase_ids?.[0];
    const p = id
      ? await api<CommercePurchase>(`${commerce}/purchases/${id}`)
      : null;
    setPurchase(p);
    setExecutionKey(p?.execution_key || crypto.randomUUID());
    setModes(p?.execution_modes || {});
  }
  async function start() {
    await run("Evaluating financial strategies", async () => {
      accept(
        await api<FinancialDecision>(
          base + "/decisions",
          natural ? { text } : { goal },
        ),
      );
      setPurchase(null);
      setNotice(
        natural
          ? "Gemini interpreted your request; financial calculations are deterministic."
          : "Structured goal evaluated without AI extraction.",
      );
    });
  }
  async function revise() {
    if (decision)
      await run(
        "Revising goal and invalidating affected approvals",
        async () => {
          accept(
            await api<FinancialDecision>(
              `${base}/decisions/${decision.id}/revise`,
              { goal },
            ),
          );
          if (purchase)
            setPurchase(
              await api<CommercePurchase>(
                `${commerce}/purchases/${purchase.id}`,
              ),
            );
          setNotice(
            "Financial goal revised. Previous approvals cannot authorize the new plan.",
          );
        },
      );
  }
  async function select(code: string) {
    if (decision)
      await run("Preparing checkout for review", async () => {
        const p = await api<CommercePurchase>(
          `${base}/decisions/${decision.id}/select`,
          { strategy: code, idempotency_key: crypto.randomUUID() },
        );
        setPurchase(p);
        setExecutionKey(crypto.randomUUID());
        setModes({});
      });
  }
  async function action(name: string, body?: unknown) {
    if (purchase)
      await run("Updating mock payment state", async () => {
        setPurchase(
          await api<CommercePurchase>(
            name === "refresh"
              ? `${commerce}/purchases/${purchase.id}`
              : `${commerce}/purchases/${purchase.id}/${name}`,
            name === "refresh"
              ? undefined
              : name === "execute"
                ? {
                    idempotency_key: executionKey || crypto.randomUUID(),
                    simulations: modes,
                  }
                : body || {},
          ),
        );
      });
  }
  async function simulate() {
    if (decision)
      await run("Running hypothetical scenario", async () => {
        const body =
          scenarioType === "price"
            ? {
                category_price_change_percent: {
                  [scenarioCategory]: scenarioValue,
                },
              }
            : scenarioType === "budget"
              ? { budget_reduction: scenarioValue }
              : scenarioType === "remove"
                ? { remove_categories: [scenarioCategory] }
                : scenarioType === "wait"
                  ? { wait_days: Number(scenarioValue) }
                  : {
                      unavailable_product_ids: [
                        decision.result.strategies
                          .find((s) => s.code === "optimized")
                          ?.plan?.items.find(
                            (l) => l.product.category === scenarioCategory,
                          )?.product.id,
                      ].filter(Boolean),
                    };
        setScenario(
          await api<FinancialScenario>(
            `${base}/decisions/${decision.id}/scenarios`,
            body,
          ),
        );
      });
  }
  const current = decision?.result,
    history = decision?.histories[selectedHistory];
  return (
    <main className="financial-app">
      <header className="finance-header">
        <Link className="brand" href="/">
          ◈ <span>IntentOS</span>
        </Link>
        <nav>
          <Link href="/">Single purchase</Link>
          <Link href="/setup">Setup planner</Link>
          <Link href="/commerce">Commerce</Link>
          <Link href="/finance" aria-current="page">
            Financial decisions
          </Link>
        </nav>
        <span className="tag">DEMO CATALOG · MOCK PAYMENTS</span>
      </header>
      <div className="finance-shell">
        <section className="finance-intro">
          <span className="eyebrow">DECISION INTELLIGENCE / PHASE 04</span>
          <h1>
            Spend with a plan.
            <br />
            <em>Keep your reserve.</em>
          </h1>
          <p>
            Compare current purchase strategies, inspect price evidence and test
            what could change. Every purchase still needs your approval.
          </p>
        </section>
        <section className="finance-panel">
          <div className="finance-card-top">
            <h2>Your financial goal</h2>
            <label className="check">
              <input
                type="checkbox"
                checked={natural}
                onChange={(e) => setNatural(e.target.checked)}
              />{" "}
              Interpret a request with Gemini
            </label>
          </div>
          <fieldset disabled={!!busy} className="finance-fieldset">
            {natural && (
              <label className="finance-wide">
                Shopping request
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={3}
                />
                <small>
                  Requires a configured Gemini API key. Structured controls
                  below work without it.
                </small>
              </label>
            )}
            <div className="finance-inputs">
              <label>
                Total available (INR)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={goal.total_budget || ""}
                  onChange={(e) =>
                    setGoal({ ...goal, total_budget: e.target.value })
                  }
                />
              </label>
              <label>
                Mandatory reserve (INR)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={goal.mandatory_reserve}
                  onChange={(e) =>
                    setGoal({ ...goal, mandatory_reserve: e.target.value })
                  }
                />
              </label>
              <label>
                Planning strategy
                <select
                  value={goal.risk_strategy}
                  onChange={(e) =>
                    setGoal({
                      ...goal,
                      risk_strategy: e.target
                        .value as FinancialGoal["risk_strategy"],
                    })
                  }
                >
                  <option value="cost_focused">Cost focused</option>
                  <option value="balanced">Balanced</option>
                  <option value="risk_averse">Risk averse</option>
                </select>
              </label>
              <label>
                Patience (days)
                <input
                  type="number"
                  min="0"
                  max="365"
                  value={goal.patience_days}
                  onChange={(e) =>
                    setGoal({ ...goal, patience_days: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                Deadline, if any
                <input
                  type="date"
                  value={goal.deadline || ""}
                  onChange={(e) =>
                    setGoal({ ...goal, deadline: e.target.value || null })
                  }
                />
              </label>
              <label>
                Waiting cost per day (INR)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={goal.opportunity_cost_per_day}
                  onChange={(e) =>
                    setGoal({
                      ...goal,
                      opportunity_cost_per_day: e.target.value,
                    })
                  }
                />
              </label>
              <label>
                Target basket total, optional (INR)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={goal.target_total || ""}
                  onChange={(e) =>
                    setGoal({ ...goal, target_total: e.target.value || null })
                  }
                />
              </label>
              <label>
                History source
                <select
                  value={goal.history_mode}
                  onChange={(e) =>
                    setGoal({
                      ...goal,
                      history_mode: e.target
                        .value as FinancialGoal["history_mode"],
                    })
                  }
                >
                  <option value="recorded">Recorded quotes only</option>
                  <option value="synthetic_demo">Synthetic demo only</option>
                </select>
              </label>
            </div>
            <div className="finance-requirements">
              {categories.map((category) => {
                const item = goal.items.find((r) => r.category === category);
                return (
                  <div className="finance-requirement" key={category}>
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={!!item}
                        onChange={(e) =>
                          setGoal({
                            ...goal,
                            items: e.target.checked
                              ? [
                                  ...goal.items,
                                  {
                                    category,
                                    quantity: 1,
                                    required: true,
                                    priority: 3,
                                    hard_constraints: [],
                                    soft_preferences: [],
                                  },
                                ]
                              : goal.items.filter(
                                  (r) => r.category !== category,
                                ),
                          })
                        }
                      />
                      {category}
                    </label>
                    {item && (
                      <>
                        <label>
                          Quantity
                          <input
                            aria-label={`${category} quantity`}
                            type="number"
                            min="1"
                            max="10"
                            value={item.quantity}
                            onChange={(e) =>
                              setGoal({
                                ...goal,
                                items: goal.items.map((r) =>
                                  r.category === category
                                    ? { ...r, quantity: Number(e.target.value) }
                                    : r,
                                ),
                              })
                            }
                          />
                        </label>
                        <label>
                          Priority
                          <select
                            value={item.priority}
                            onChange={(e) =>
                              setGoal({
                                ...goal,
                                items: goal.items.map((r) =>
                                  r.category === category
                                    ? { ...r, priority: Number(e.target.value) }
                                    : r,
                                ),
                              })
                            }
                          >
                            {[1, 2, 3, 4, 5].map((n) => (
                              <option key={n}>{n}</option>
                            ))}
                          </select>
                        </label>
                        <label className="check">
                          <input
                            type="checkbox"
                            checked={item.required}
                            onChange={(e) =>
                              setGoal({
                                ...goal,
                                items: goal.items.map((r) =>
                                  r.category === category
                                    ? { ...r, required: e.target.checked }
                                    : r,
                                ),
                              })
                            }
                          />
                          Required
                        </label>
                      </>
                    )}
                    <label>
                      Category cap (INR)
                      <input
                        aria-label={`${category} spending limit`}
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="No separate cap"
                        value={goal.category_limits[category] ?? ""}
                        onChange={(e) => {
                          const limits = { ...goal.category_limits };
                          if (e.target.value === "") delete limits[category];
                          else limits[category] = e.target.value;
                          setGoal({ ...goal, category_limits: limits });
                        }}
                      />
                    </label>
                  </div>
                );
              })}
            </div>
            <p className="finance-muted">
              The structured starter requires 16 GB RAM for the laptop. Existing
              specifications remain attached when you revise a goal.
            </p>
            <div className="finance-actions">
              <button className="primary" onClick={start}>
                Evaluate new decision
              </button>
              {decision && (
                <button className="secondary" onClick={revise}>
                  Apply financial changes · invalidate approvals
                </button>
              )}
              {decision && (
                <button
                  className="secondary"
                  onClick={() =>
                    run("Refreshing demo quotes and replanning", async () => {
                      await api(`${commerce}/offers/refresh`, {
                        offer_ids: Object.keys(decision.histories),
                      });
                      accept(
                        await api<FinancialDecision>(
                          `${base}/decisions/${decision.id}/replan`,
                          {},
                        ),
                      );
                      if (purchase)
                        setPurchase(
                          await api<CommercePurchase>(
                            `${commerce}/purchases/${purchase.id}`,
                          ),
                        );
                      setNotice(
                        "The saved goal was replanned using refreshed demo quotes. Fresh approval is required. This is not live merchant verification.",
                      );
                    })
                  }
                >
                  Refresh demo quotes &amp; replan
                </button>
              )}
              <button
                className="secondary"
                onClick={() =>
                  run("Creating labeled synthetic history", async () => {
                    const r = await api<{ created: number }>(
                      base + "/demo/synthetic-history",
                      {},
                    );
                    setNotice(
                      `${r.created} synthetic samples created. Select synthetic history and evaluate a new decision to use them.`,
                    );
                  })
                }
              >
                Create synthetic history fixture
              </button>
            </div>
          </fieldset>
        </section>
        <section className="finance-restore">
          <label>
            Saved decision ID
            <input
              value={restoreId}
              onChange={(e) => setRestoreId(e.target.value)}
            />
          </label>
          <button
            className="secondary"
            disabled={!!busy || !restoreId}
            onClick={() =>
              run("Restoring persisted decision", async () => {
                await restore(
                  await api<FinancialDecision>(
                    `${base}/decisions/${restoreId}`,
                  ),
                );
              })
            }
          >
            Restore
          </button>
          <button
            className="secondary"
            disabled={!!busy || !restoreId}
            onClick={() =>
              run("Resuming financial workflow", async () =>
                restore(
                  await api<FinancialDecision>(
                    `${base}/decisions/${restoreId}/resume`,
                    {},
                  ),
                ),
              )
            }
          >
            Resume workflow
          </button>
        </section>
        {busy && (
          <p className="finance-status" role="status">
            {busy}…
          </p>
        )}
        {error && (
          <p className="finance-error" role="alert">
            {error}
          </p>
        )}
        {notice && (
          <p className="finance-status" role="status">
            {notice}
          </p>
        )}
        {decision && current && (
          <>
            <section className="finance-result-heading">
              <span className="eyebrow">
                {decision.status.replaceAll("_", " ")} ·{" "}
                {decision.workflow.completed.length} WORKFLOW STEPS SAVED
              </span>
              <h2>Your money, allocated deliberately.</h2>
              <p>{current.explanation}</p>
              {current.reserve && (
                <div className="finance-budget">
                  {[
                    ["Available", current.reserve.available],
                    ["Untouched reserve", current.reserve.mandatory_reserve],
                    ["Spendable", current.reserve.spendable],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <small>{label}</small>
                      <strong>{exactMoney(value)}</strong>
                    </div>
                  ))}
                </div>
              )}
              {current.reserve?.encumbered && (
                <p className="finance-muted">
                  Existing commitments: {exactMoney(current.reserve.encumbered)}{" "}
                  · Capacity for new purchases:{" "}
                  {exactMoney(
                    current.reserve.new_purchase_capacity ||
                      current.reserve.spendable,
                  )}
                  . Refund-pending and unknown payments remain encumbered.
                </p>
              )}
              {!!current.missing_information?.length && (
                <p>Missing: {current.missing_information.join(", ")}</p>
              )}
            </section>
            <div className="finance-strategies">
              {current.strategies.map((s) => (
                <PlanCard
                  key={s.code}
                  strategy={s}
                  busy={!!busy}
                  onSelect={select}
                />
              ))}
            </div>
            <div className="finance-evidence-grid">
              <section className="finance-panel">
                <h2>Buy now or wait?</h2>
                <span className="tag">
                  {current.wait?.status.replaceAll("_", " ")}
                </span>
                <p>{current.wait?.explanation}</p>
                {current.wait?.target_total && (
                  <dl className="finance-facts">
                    <dt>Conditional target</dt>
                    <dd>{exactMoney(current.wait.target_total)}</dd>
                    <dt>Waiting opportunity cost</dt>
                    <dd>{exactMoney(current.wait.opportunity_cost!)}</dd>
                    <dt>Conditional net difference</dt>
                    <dd>{current.wait.conditional_net_difference} INR</dd>
                  </dl>
                )}
                {current.wait?.stock_at_risk && (
                  <p>
                    At least one selected offer has low stock; availability
                    after waiting is unknown.
                  </p>
                )}
                <p>
                  No future discount probability or guaranteed saving is
                  estimated.
                </p>
                <details>
                  <summary>Assumptions and change triggers</summary>
                  <ul>
                    {current.assumptions?.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                  <h3>Re-evaluate when</h3>
                  <ul>
                    {current.change_triggers?.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                </details>
              </section>
              <section className="finance-panel">
                <h2>Price evidence</h2>
                <label>
                  Offer history
                  <select
                    value={selectedHistory}
                    onChange={(e) => setSelectedHistory(e.target.value)}
                  >
                    {Object.keys(decision.histories).map((id) => (
                      <option key={id} value={id}>
                        {id}
                      </option>
                    ))}
                  </select>
                </label>
                {history && <HistoryChart history={history} />}
              </section>
            </div>
            <section className="finance-panel">
              <span className="eyebrow">
                HYPOTHETICAL · NO MARKET CHANGES OR PAYMENTS
              </span>
              <h2>What would change the plan?</h2>
              <div className="finance-inputs">
                <label>
                  Scenario
                  <select
                    value={scenarioType}
                    onChange={(e) => {
                      setScenarioType(e.target.value);
                      setScenarioValue(
                        e.target.value === "budget"
                          ? "15000"
                          : e.target.value === "wait"
                            ? "14"
                            : "10",
                      );
                    }}
                  >
                    <option value="price">
                      Change category base prices (%)
                    </option>
                    <option value="budget">
                      Reduce available budget (INR)
                    </option>
                    <option value="remove">Remove a category</option>
                    <option value="wait">Wait this many days</option>
                    <option value="unavailable">
                      Selected category product unavailable
                    </option>
                  </select>
                </label>
                <label>
                  Category
                  <select
                    value={scenarioCategory}
                    onChange={(e) => setScenarioCategory(e.target.value)}
                  >
                    {categories.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
                {["price", "budget", "wait"].includes(scenarioType) && (
                  <label>
                    Scenario value
                    <input
                      type="number"
                      step={scenarioType === "wait" ? "1" : "0.01"}
                      value={scenarioValue}
                      onChange={(e) => setScenarioValue(e.target.value)}
                    />
                  </label>
                )}
              </div>
              <button
                className="secondary"
                disabled={!!busy}
                onClick={simulate}
              >
                Run hypothetical scenario
              </button>
              {scenario && (
                <div className="finance-scenario">
                  <span className="tag">
                    HYPOTHETICAL RESULT · {scenario.result.status}
                  </span>
                  <p>{scenario.result.explanation}</p>
                  {scenario.result.wait && (
                    <p>
                      Waiting: {scenario.result.wait.status} ·{" "}
                      {scenario.result.wait.explanation}
                    </p>
                  )}
                  <div className="finance-strategies">
                    {scenario.result.strategies.map((s) => (
                      <PlanCard key={s.code} strategy={s} busy={!!busy} />
                    ))}
                  </div>
                </div>
              )}
              {!!decision.scenarios.length && (
                <details>
                  <summary>
                    {decision.scenarios.length} previously saved scenarios
                  </summary>
                  {decision.scenarios.map((s) => (
                    <button
                      key={s.id}
                      className="secondary"
                      onClick={() => setScenario(s)}
                    >
                      {s.id.slice(0, 8)} · {s.result.status}
                    </button>
                  ))}
                </details>
              )}
            </section>
            <p className="finance-muted">
              Decision {decision.id} · Solver comparison runtime{" "}
              {current.runtime_ms} ms. Demo computations are not evidence of
              real-world savings.
            </p>
            {decision && decision.purchase_ids?.length > 0 && (
              <section className="finance-restore">
                <label>
                  Saved transaction
                  <select
                    value={purchase?.id || ""}
                    onChange={(e) =>
                      run("Restoring transaction", async () => {
                        const p = await api<CommercePurchase>(
                          `${commerce}/purchases/${e.target.value}`,
                        );
                        setPurchase(p);
                        setExecutionKey(p.execution_key || crypto.randomUUID());
                        setModes(p.execution_modes || {});
                      })
                    }
                  >
                    <option value="" disabled>
                      Choose a transaction
                    </option>
                    {decision.purchase_ids.map((id) => (
                      <option key={id}>{id}</option>
                    ))}
                  </select>
                </label>
              </section>
            )}
            {purchase && (
              <MerchantPayments
                key={purchase.id}
                purchase={purchase}
                busy={!!busy}
                modes={modes}
                onMode={(id, mode) => setModes({ ...modes, [id]: mode })}
                onAction={action}
                onRetry={(id) =>
                  run("Retrying confirmed failed mock payment", async () => {
                    setPurchase(
                      await api<CommercePurchase>(
                        `${commerce}/suborders/${id}/retry`,
                        {
                          idempotency_key: crypto.randomUUID(),
                          simulation:
                            modes[
                              purchase.suborders.find((s) => s.id === id)
                                ?.merchant_id || ""
                            ] || "success",
                        },
                      ),
                    );
                  })
                }
                onResolve={(id, outcome) =>
                  run("Resolving mock ledger outcome", async () => {
                    await api(`${commerce}/demo/attempts/${id}/resolve`, {
                      outcome,
                    });
                    setNotice(
                      "Mock ledger updated. Reconcile the purchase before retrying.",
                    );
                  })
                }
              />
            )}
          </>
        )}
        <footer className="finance-footer">
          IntentOS · Local commerce intelligence. Demo offers, explicit
          provenance, mock payments.
        </footer>
      </div>
    </main>
  );
}
