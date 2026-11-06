"use client";
import { useEffect, useState } from "react";
import { api, ApiError, money, AuditEvent } from "@/lib/api";
import { categories, MultiIntent, Plan, Cart, BundleOrder } from "@/lib/multi";
import BudgetAllocation from "./BudgetAllocation";
import PlanCart from "./PlanCart";

const initial: MultiIntent = {
  total_budget: 100000,
  currency: "INR",
  items: categories.map((category) => ({
    category,
    quantity: 1,
    required: true,
    priority: category === "laptop" ? 5 : 3,
    hard_constraints: [],
    soft_preferences: [],
  })),
  priorities: ["Laptop performance", "Good value"],
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
  use_case: "coding and development",
  missing_information: [],
};
export default function MultiWorkspace() {
  const [text, setText] = useState(
    "Build my complete coding setup under ₹1,00,000. I need a laptop, monitor, keyboard, mouse, and headphones. Prioritize laptop performance and good value.",
  );
  const [manual, setManual] = useState(false);
  const [intent, setIntent] = useState<MultiIntent>(initial);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [index, setIndex] = useState(0);
  const [cart, setCart] = useState<Cart | null>(null);
  const [order, setOrder] = useState<BundleOrder | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [approved, setApproved] = useState(false);
  const [failure, setFailure] = useState(false);
  const [payKey, setPayKey] = useState("");
  const [revisedId, setRevisedId] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [change, setChange] = useState("unavailable");
  const [changedProduct, setChangedProduct] = useState("");
  useEffect(() => {
    try {
      setHistory(
        JSON.parse(localStorage.getItem("intentos-multi-plans") || "[]"),
      );
    } catch {
      setHistory([]);
    }
  }, []);
  useEffect(() => {
    if (!order || !plan) return;
    try {
      const saved = JSON.parse(
        localStorage.getItem("intentos-plan-orders") || "{}",
      );
      saved[plan.id] = order.id;
      localStorage.setItem("intentos-plan-orders", JSON.stringify(saved));
    } catch {
      /* Order remains persisted on the server if browser storage is unavailable. */
    }
  }, [order, plan]);
  function remember(id: string) {
    setHistory((previous) => {
      const next = [id, ...previous.filter((v) => v !== id)].slice(0, 15);
      localStorage.setItem("intentos-multi-plans", JSON.stringify(next));
      return next;
    });
  }
  async function loadPlan(next: Plan) {
    setPlan(next);
    setIntent(next.intent);
    setIndex(0);
    setCart(null);
    setOrder(null);
    setEvents([]);
    setApproved(false);
    setFailure(false);
    setPayKey(crypto.randomUUID());
    setRevisedId("");
    setChangedProduct(next.result.combinations[0]?.items[0]?.product.id || "");
    remember(next.id);
    try {
      const saved = JSON.parse(
        localStorage.getItem("intentos-plan-orders") || "{}",
      );
      const savedId = next.order_ids?.[0] || saved[next.id];
      if (typeof savedId === "string") {
        const restored = await api<BundleOrder>(`/api/v1/orders/${savedId}`);
        await refreshOrder(restored.id);
        if (restored.cart_id) {
          const restoredCart = await api<Cart>(
            `/api/v1/carts/${restored.cart_id}`,
          );
          setCart(restoredCart);
          setIndex(restoredCart.alternative_index || 0);
        }
      }
    } catch {
      setNotice(
        "Saved order could not be restored. The plan is still available; verify backend status before creating another order.",
      );
    }
  }
  async function refreshOrder(id: string) {
    const [next, audit] = await Promise.all([
      api<BundleOrder>(`/api/v1/orders/${id}`),
      api<AuditEvent[]>(`/api/v1/orders/${id}/events`),
    ]);
    setOrder(next);
    setEvents(audit);
  }
  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      if (
        e instanceof ApiError &&
        e.detail &&
        typeof e.detail === "object" &&
        "revised_plan_id" in e.detail
      ) {
        const id = e.detail.revised_plan_id;
        if (typeof id === "string") {
          setRevisedId(id);
          setApproved(false);
          setNotice(
            "The previous plan is invalid. A revised plan is available and needs fresh approval.",
          );
          if (order) await refreshOrder(order.id).catch(() => {});
        }
      }
    } finally {
      setBusy("");
    }
  }
  async function analyze() {
    await run(
      manual
        ? "Optimizing structured requirements"
        : "Parsing with Gemini and optimizing",
      async () => {
        const next = await api<Plan>(
          manual ? "/api/v1/plans" : "/api/v1/multi/analyze",
          manual ? { intent } : { text },
        );
        await loadPlan(next);
        setNotice("");
      },
    );
  }
  async function choose() {
    if (!plan) return;
    await run("Preparing selected cart", async () => {
      const next = await api<Cart>("/api/v1/carts", {
        plan_id: plan.id,
        alternative_index: index,
      });
      setCart(next);
      setOrder(null);
      setEvents([]);
      setApproved(false);
      setNotice(
        "Cart prepared from verified catalog snapshots. Review all items before creating an order.",
      );
    });
  }
  async function edit(oldId: string, replacement?: string) {
    if (!cart) return;
    await run("Validating cart change", async () => {
      const ids = cart.snapshot.items
        .flatMap((line) =>
          Array.from({ length: line.quantity }, () => line.product.id),
        )
        .flatMap((id) =>
          id !== oldId ? [id] : replacement ? [replacement] : [],
        );
      setCart(
        await api<Cart>(`/api/v1/carts/${cart.id}/items`, {
          product_ids: ids,
          expected_version: cart.version,
        }),
      );
      setApproved(false);
    });
  }
  async function createOrder() {
    if (!cart) return;
    await run("Creating multi-item order", async () => {
      const next = await api<BundleOrder>("/api/v1/multi/orders", {
        cart_id: cart.id,
        cart_version: cart.version,
        idempotency_key: crypto.randomUUID(),
      });
      await refreshOrder(next.id);
      setCart({ ...cart, status: "ORDERED" });
      setApproved(false);
      setPayKey(crypto.randomUUID());
    });
  }
  async function validate() {
    if (!plan) return;
    await run("Checking catalog freshness", async () => {
      const result = await api<{ valid: boolean; revised_plan_id?: string }>(
        `/api/v1/plans/${plan.id}/validate`,
        {},
      );
      if (result.valid)
        setNotice(
          "Catalog snapshots are current. Your selection has not changed.",
        );
      else {
        setRevisedId(result.revised_plan_id || "");
        setApproved(false);
        setNotice(
          "Catalog changed. The original plan is invalid; review the revised plan and approve a new order.",
        );
        if (order) await refreshOrder(order.id);
      }
    });
  }
  async function replan() {
    if (!plan) return;
    await run("Replanning budget and preferences", async () => {
      const next = await api<Plan>(`/api/v1/plans/${plan.id}/replan`, {
        intent,
      });
      setRevisedId(next.id);
      setApproved(false);
      setNotice(
        "A revised plan is ready. Previous approvals have been cancelled. Review it before creating a new order.",
      );
      if (order) await refreshOrder(order.id);
    });
  }
  const combination = cart?.snapshot || plan?.result.combinations[index];
  const invalid = !!revisedId || plan?.status === "INVALIDATED";
  return (
    <main>
      <aside>
        <a className="brand" href="/">
          i<span>IntentOS</span>
          <sup>β</sup>
        </a>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <a className="nav-link" href="/">
          Single-product agent
        </a>
        <a className="nav-active" href="/setup">
          ◈ <span>Setup optimizer</span>
        </a>
        <a className="nav-link" href="/commerce">
          Commerce offers & payment orchestration ↗
        </a>
        <a className="nav-link" href="/finance">
          Financial decisions
        </a>
        <div className="history-label">RECENT PLANS</div>
        <div className="history">
          {history.length === 0 ? (
            <p>Your plans will appear here.</p>
          ) : (
            history.map((id) => (
              <button
                key={id}
                disabled={!!busy}
                onClick={() =>
                  run("Loading saved plan", async () =>
                    loadPlan(await api<Plan>(`/api/v1/plans/${id}`)),
                  )
                }
              >
                ↗ {id.slice(0, 8)}
              </button>
            ))
          )}
        </div>
        <div className="sidebar-footer">Local demo · No real funds</div>
      </aside>
      <section className="workspace">
        <header>
          <span>Workspace / Setup optimizer</span>
          <span className="header-badge">OR-TOOLS · MOCK PAYMENTS</span>
        </header>
        <div className="content">
          <div className="intro">
            <div>
              <p className="eyebrow">ONE BUDGET. A COMPLETE SETUP.</p>
              <h1>Make every item count.</h1>
              <p>
                Optimize a whole shopping list, compare trade-offs, and approve
                the final cart.
              </p>
            </div>
            <div className="version">
              PHASE 02<span>Financial optimization</span>
            </div>
          </div>
          <section className="request-panel">
            <div className="section-title">
              <span className="number">01</span>
              <h2>Your purchasing goal</h2>
            </div>
            <div className="mode-tabs">
              <button
                className={!manual ? "primary" : "secondary"}
                disabled={!!busy}
                onClick={() => setManual(false)}
              >
                Natural language · Gemini
              </button>
              <button
                className={manual ? "primary" : "secondary"}
                disabled={!!busy}
                onClick={() => setManual(true)}
              >
                Structured requirements
              </button>
            </div>
            {!manual ? (
              <>
                <label htmlFor="multi-request" className="sr-only">
                  Multi-product purchasing goal
                </label>
                <textarea
                  id="multi-request"
                  disabled={!!busy}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
                <p className="demo-note">
                  Gemini extracts requirements. OR-Tools computes the
                  combinations. A Gemini API key is required for this mode.
                </p>
              </>
            ) : (
              <>
                <p className="demo-note">
                  Explicit structured input goes directly to the optimizer. No
                  AI extraction is claimed in this mode.
                </p>
                <label className="budget-input">
                  Total budget (INR)
                  <input
                    type="number"
                    min={1}
                    max={10000000}
                    value={intent.total_budget || ""}
                    onChange={(e) =>
                      setIntent({
                        ...intent,
                        total_budget: Number(e.target.value) || null,
                      })
                    }
                  />
                </label>
                <div className="requirement-grid">
                  {categories.map((category) => {
                    const item = intent.items.find(
                      (r) => r.category === category,
                    );
                    return (
                      <div key={category}>
                        <label>
                          <input
                            type="checkbox"
                            checked={!!item}
                            onChange={(e) =>
                              setIntent({
                                ...intent,
                                items: e.target.checked
                                  ? [
                                      ...intent.items,
                                      {
                                        category,
                                        quantity: 1,
                                        required: true,
                                        priority: 3,
                                        hard_constraints: [],
                                        soft_preferences: [],
                                      },
                                    ]
                                  : intent.items.filter(
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
                              Qty
                              <input
                                aria-label={`${category} quantity`}
                                type="number"
                                min={1}
                                max={10}
                                value={item.quantity}
                                onChange={(e) =>
                                  setIntent({
                                    ...intent,
                                    items: intent.items.map((r) =>
                                      r.category === category
                                        ? {
                                            ...r,
                                            quantity: Number(e.target.value),
                                          }
                                        : r,
                                    ),
                                  })
                                }
                              />
                            </label>
                            <label>
                              Priority
                              <select
                                aria-label={`${category} priority`}
                                value={item.priority}
                                onChange={(e) =>
                                  setIntent({
                                    ...intent,
                                    items: intent.items.map((r) =>
                                      r.category === category
                                        ? {
                                            ...r,
                                            priority: Number(e.target.value),
                                          }
                                        : r,
                                    ),
                                  })
                                }
                              >
                                {[1, 2, 3, 4, 5].map((n) => (
                                  <option key={n} value={n}>
                                    {n}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label>
                              <input
                                type="checkbox"
                                checked={item.required}
                                onChange={(e) =>
                                  setIntent({
                                    ...intent,
                                    items: intent.items.map((r) =>
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
                      </div>
                    );
                  })}
                </div>
              </>
            )}
            <div className="request-bottom">
              <span>
                Demo catalog · Five categories · Server-side financial
                calculations
              </span>
              <button
                className="primary"
                disabled={!!busy || (!manual && text.trim().length < 10)}
                onClick={analyze}
              >
                {manual ? "Optimize structured requirements" : "Build my setup"}{" "}
                ↗
              </button>
            </div>
          </section>
          {busy && (
            <p className="loading" role="status">
              <span className="live-dot" />
              {busy}…
            </p>
          )}
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {notice && (
            <div className="notice" role="status">
              {notice}
            </div>
          )}
          {revisedId && (
            <button
              className="primary"
              disabled={!!busy}
              onClick={() =>
                run("Loading revised plan", async () =>
                  loadPlan(await api<Plan>(`/api/v1/plans/${revisedId}`)),
                )
              }
            >
              Review revised plan · Fresh approval required
            </button>
          )}
          {plan && (
            <>
              <section className="intent-summary">
                <div className="workflow-heading">
                  <h2>Extracted requirements · Revision {plan.revision}</h2>
                  <span>{plan.status}</span>
                </div>
                <p>
                  Budget:{" "}
                  {plan.intent.total_budget
                    ? money(plan.intent.total_budget)
                    : "Missing"}{" "}
                  · {plan.intent.currency} · {plan.intent.use_case}
                </p>
                <div className="requirement-tags">
                  {plan.intent.items.map((item) => (
                    <div key={item.category}>
                      <strong>
                        {item.quantity} × {item.category}
                      </strong>
                      <span>
                        {item.required ? "Required" : "Optional"} · Priority{" "}
                        {item.priority}/5
                      </span>
                      {item.hard_constraints.map((rule, i) => (
                        <small key={i}>
                          Must: {rule.field} {rule.operator}{" "}
                          {String(rule.value)}
                        </small>
                      ))}
                      {item.soft_preferences.map((rule, i) => (
                        <small key={i}>
                          Prefer: {rule.field} {rule.operator}{" "}
                          {String(rule.value)}
                        </small>
                      ))}
                    </div>
                  ))}
                </div>
                <p className="demo-note">
                  Priorities:{" "}
                  {plan.intent.priorities.join(", ") ||
                    "Default balanced weights"}
                  . Review these before checkout.
                </p>
                <details>
                  <summary>Completed workflow stages</summary>
                  <p>{plan.workflow.steps.join(" → ")}</p>
                </details>
              </section>
              {plan.changes.length > 0 && (
                <div className="notice">
                  <strong>What changed</strong>
                  {plan.changes.map((reason, i) => (
                    <p key={i}>{reason}</p>
                  ))}
                </div>
              )}
              {plan.status === "NEEDS_DETAILS" && (
                <div className="notice">
                  Please clarify: {plan.result.missing_information.join(", ")}
                </div>
              )}
              {["INFEASIBLE", "SOLVER_LIMIT"].includes(plan.status) && (
                <div className="notice">
                  {plan.status === "INFEASIBLE"
                    ? "No combination meets the budget, quantities and hard constraints."
                    : "The solver reached its limit without a valid result."}{" "}
                  Update the request or budget and try again.
                </div>
              )}
              {combination && (
                <>
                  <div className="results-heading">
                    <div>
                      <p className="eyebrow">OPTIMIZED PURCHASE PLAN</p>
                      <h2>A balanced cart, within budget.</h2>
                    </div>
                    <span className="tag">DEMO DATA</span>
                  </div>
                  <div className="alternative-plans">
                    {plan.result.combinations.map((candidate, i) => (
                      <button
                        className={i === index ? "selected-plan" : "secondary"}
                        key={i}
                        disabled={!!busy || !!cart || invalid}
                        onClick={() => {
                          setIndex(i);
                          setChangedProduct(
                            candidate.items[0]?.product.id || "",
                          );
                        }}
                      >
                        <strong>
                          {i === 0 ? "Best utility" : `Alternative ${i}`}
                        </strong>
                        <span>{money(candidate.total_cost)}</span>
                        <small>
                          {candidate.utility_score.toLocaleString()} utility
                        </small>
                      </button>
                    ))}
                  </div>
                  <BudgetAllocation
                    combination={combination}
                    budget={plan.intent.total_budget!}
                  />
                  <PlanCart
                    combination={combination}
                    candidates={plan.result.candidates}
                    editable={cart?.status === "ACTIVE" && !invalid}
                    busy={!!busy}
                    onReplace={(id, replacement) => edit(id, replacement)}
                    onRemove={(id) => edit(id)}
                  />
                  <details className="plan-tradeoffs">
                    <summary>Allocation trade-offs</summary>
                    {combination.tradeoffs.map((tradeoff, i) => (
                      <p key={i}>{tradeoff}</p>
                    ))}
                  </details>
                  <div className="cart-controls">
                    {!cart && (
                      <button
                        className="primary"
                        disabled={!!busy || invalid}
                        onClick={choose}
                      >
                        Use this plan & prepare cart
                      </button>
                    )}
                    {cart?.status === "ACTIVE" && (
                      <>
                        <button
                          className="primary"
                          disabled={!!busy || invalid}
                          onClick={createOrder}
                        >
                          Create order · {money(cart.snapshot.total_cost)}
                        </button>
                        <button
                          className="secondary"
                          disabled={!!busy || invalid}
                          onClick={() => {
                            setCart(null);
                            setOrder(null);
                            setApproved(false);
                          }}
                        >
                          Inspect alternatives
                        </button>
                      </>
                    )}
                    <button
                      className="secondary"
                      disabled={!!busy || invalid}
                      onClick={validate}
                    >
                      Check catalog freshness
                    </button>
                  </div>
                </>
              )}
              {order && (
                <section className="checkout">
                  <div className="section-title">
                    <span className="number">02</span>
                    <h2>Review & authorize multi-item order</h2>
                    <span className="tag">{order.status}</span>
                  </div>
                  <p>
                    Order {order.id} · Server total {money(order.amount)}
                  </p>
                  {order.status === "PENDING_APPROVAL" && !invalid && (
                    <>
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={approved}
                          onChange={(e) => setApproved(e.target.checked)}
                        />
                        I explicitly approve every listed product, quantity,
                        seller and the total of {money(order.amount)} for this
                        simulated purchase.
                      </label>
                      <button
                        className="primary"
                        disabled={!!busy || !approved}
                        onClick={() =>
                          run("Recording explicit approval", async () => {
                            await api(`/api/v1/orders/${order.id}/approve`, {
                              approved: true,
                            });
                            await refreshOrder(order.id);
                          })
                        }
                      >
                        Approve final cart
                      </button>
                    </>
                  )}
                  {order.status === "APPROVED" && !invalid && (
                    <>
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={failure}
                          onChange={(e) => setFailure(e.target.checked)}
                        />
                        Simulate payment failure
                      </label>
                      <button
                        className="primary"
                        disabled={!!busy}
                        onClick={() =>
                          run("Processing mock payment", async () => {
                            await api(`/api/v1/orders/${order.id}/pay`, {
                              idempotency_key: payKey,
                              simulate_failure: failure,
                            });
                            await refreshOrder(order.id);
                          })
                        }
                      >
                        Pay {money(order.amount)} · simulated
                      </button>
                    </>
                  )}
                  {["PENDING_APPROVAL", "APPROVED"].includes(order.status) && (
                    <button
                      className="secondary cancel"
                      disabled={!!busy}
                      onClick={() =>
                        run("Cancelling order", async () => {
                          await api(`/api/v1/orders/${order.id}/cancel`, {});
                          await refreshOrder(order.id);
                        })
                      }
                    >
                      Cancel order
                    </button>
                  )}
                  {order.payment && (
                    <div className="notice" role="status">
                      {order.payment.status === "PAID"
                        ? "Simulated payment completed. No real funds moved."
                        : "Simulated payment failed. No real funds moved."}
                      <p>Transaction {order.payment.id}</p>
                    </div>
                  )}
                  <div className="audit">
                    <h3>Persisted transaction history</h3>
                    {events.map((event) => (
                      <div key={event.id}>
                        <span className="live-dot" />
                        <span>
                          {event.event.replaceAll("_", " ")}
                          <small>
                            {new Date(event.created_at).toLocaleString()}
                          </small>
                        </span>
                      </div>
                    ))}
                  </div>
                  <button
                    className="secondary"
                    disabled={!!busy}
                    onClick={() =>
                      run("Refreshing order", () => refreshOrder(order.id))
                    }
                  >
                    Refresh order status
                  </button>
                  {["PAYMENT_FAILED", "CANCELLED", "PAID"].includes(
                    order.status,
                  ) &&
                    !invalid && (
                      <button
                        className="secondary cancel"
                        disabled={!!busy}
                        onClick={() => {
                          setCart(null);
                          setOrder(null);
                          setEvents([]);
                          setApproved(false);
                        }}
                      >
                        Prepare a new cart
                      </button>
                    )}
                </section>
              )}
              <section className="replan-controls">
                <h2>Replan with a changed budget or preference</h2>
                <div>
                  <label>
                    Total budget (INR)
                    <input
                      type="number"
                      min={1}
                      max={10000000}
                      value={intent.total_budget || ""}
                      onChange={(e) =>
                        setIntent({
                          ...intent,
                          total_budget: Number(e.target.value) || null,
                        })
                      }
                    />
                  </label>
                  <label>
                    Spending preference
                    <select
                      value={intent.spending_preference}
                      onChange={(e) =>
                        setIntent({
                          ...intent,
                          spending_preference: e.target.value,
                        })
                      }
                    >
                      <option value="balanced">Balanced</option>
                      <option value="quality">Quality</option>
                      <option value="savings">Savings</option>
                    </select>
                  </label>
                  <button
                    className="secondary"
                    disabled={!!busy || invalid}
                    onClick={replan}
                  >
                    Re-optimize & invalidate previous approval
                  </button>
                </div>
              </section>
              {combination && !invalid && (
                <details className="demo-simulator">
                  <summary>Demo catalog change simulator</summary>
                  <p>
                    Changes real local demonstration records. The next freshness
                    check or payment triggers automatic replanning.
                  </p>
                  <label>
                    Selected product
                    <select
                      value={changedProduct}
                      onChange={(e) => setChangedProduct(e.target.value)}
                    >
                      {combination.items.map((line) => (
                        <option key={line.product.id} value={line.product.id}>
                          {line.product.model}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Change
                    <select
                      value={change}
                      onChange={(e) => setChange(e.target.value)}
                    >
                      <option value="unavailable">Product unavailable</option>
                      <option value="price_increase">Price + INR 1,000</option>
                      <option value="price_decrease">Price - INR 1,000</option>
                      <option value="seller_unavailable">
                        Seller unavailable
                      </option>
                    </select>
                  </label>
                  <button
                    className="secondary"
                    disabled={!!busy || !changedProduct}
                    onClick={() =>
                      run("Changing demo catalog", async () => {
                        await api(`/api/v1/plans/${plan.id}/simulate-change`, {
                          product_id: changedProduct,
                          change,
                        });
                        setNotice(
                          "Demo catalog changed. Check freshness or attempt checkout to see automatic replanning.",
                        );
                      })
                    }
                  >
                    Apply demo change
                  </button>
                </details>
              )}
            </>
          )}
          <footer>
            <span>IntentOS / Decisions you can inspect.</span>
            <span>DEMO CATALOG · CP-SAT OPTIMIZATION · EXPLICIT APPROVAL</span>
          </footer>
        </div>
      </section>
    </main>
  );
}
