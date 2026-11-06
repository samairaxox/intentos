"use client";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { categories } from "@/lib/multi";
import {
  CommerceIntent,
  CommerceSession,
  CommercePlan,
  CommercePurchase,
  CommerceTrace,
  SessionResult,
  Simulation,
} from "@/lib/commerce";
import CommercePlanPanel from "./CommercePlanPanel";
import MerchantPayments from "./MerchantPayments";
const base = "/api/v1/commerce";
const initial: CommerceIntent = {
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
  use_case: "coding workstation",
  missing_information: [],
};
export default function CommerceWorkspace() {
  const [manual, setManual] = useState(false),
    [text, setText] = useState(
      "Build a coding workstation under ₹1,00,000 with a laptop, monitor, keyboard, mouse and headphones. Prioritize performance and value.",
    );
  const [intent, setIntent] = useState<CommerceIntent>(initial),
    [session, setSession] = useState<CommerceSession | null>(null),
    [plan, setPlan] = useState<CommercePlan | null>(null),
    [purchase, setPurchase] = useState<CommercePurchase | null>(null);
  const [index, setIndex] = useState(0),
    [traces, setTraces] = useState<CommerceTrace[]>([]),
    [history, setHistory] = useState<string[]>([]),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [revisedId, setRevisedId] = useState("");
  const [modes, setModes] = useState<Record<string, Simulation>>({}),
    [executionKey, setExecutionKey] = useState(""),
    [updateText, setUpdateText] = useState(
      "Actually, I prefer something lighter.",
    ),
    [budget, setBudget] = useState(100000),
    [changeId, setChangeId] = useState(""),
    [change, setChange] = useState("price_increase"),
    [providerStatus, setProviderStatus] = useState(
      "Verifying provider configuration…",
    );
  const retryKeys = useRef<Record<string, string>>({}),
    purchaseKey = useRef("");
  useEffect(() => {
    try {
      setHistory(
        JSON.parse(localStorage.getItem("intentos-commerce-sessions") || "[]"),
      );
    } catch {}
    api<{ payment_provider: string }>(base + "/providers")
      .then((s) =>
        setProviderStatus(
          `Demo discovery active · Live integration pending · Payments: ${s.payment_provider}`,
        ),
      )
      .catch(() =>
        setProviderStatus("Backend unavailable; provider status unverified"),
      );
  }, []);
  function remember(id: string) {
    setHistory((previous) => {
      const next = [id, ...previous.filter((x) => x !== id)].slice(0, 15);
      try {
        localStorage.setItem(
          "intentos-commerce-sessions",
          JSON.stringify(next),
        );
      } catch {}
      return next;
    });
  }
  async function refreshTraces(id = session?.id) {
    if (id)
      setTraces(await api<CommerceTrace[]>(`${base}/sessions/${id}/traces`));
  }
  function acceptPurchase(next: CommercePurchase) {
    setPurchase(next);
    setExecutionKey(
      next.execution_key ||
        (next.id === purchase?.id && executionKey
          ? executionKey
          : crypto.randomUUID()),
    );
    setModes((previous) =>
      next.execution_key
        ? next.execution_modes
        : next.id === purchase?.id
          ? previous
          : (Object.fromEntries(
              next.suborders.map((s) => [s.merchant_id, "success"]),
            ) as Record<string, Simulation>),
    );
  }
  async function loadPlan(next: CommercePlan) {
    setPlan(next);
    setIndex(0);
    setPurchase(null);
    setRevisedId("");
    purchaseKey.current = crypto.randomUUID();
    setChangeId(next.result.combinations?.[0]?.items[0]?.offer.id || "");
    if (next.purchase_ids.length)
      acceptPurchase(
        await api<CommercePurchase>(
          `${base}/purchases/${next.purchase_ids[0]}`,
        ),
      );
  }
  async function acceptResult(result: SessionResult) {
    setSession(result.session);
    setIntent(result.session.intent);
    setBudget(result.session.intent.total_budget || 100000);
    remember(result.session.id);
    await loadPlan(result.plan);
    await refreshTraces(result.session.id);
  }
  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      if (e instanceof ApiError && e.detail && typeof e.detail === "object") {
        const d = e.detail as {
          revised_plan_id?: string;
          session_id?: string;
          plan_id?: string;
        };
        try {
          if (d.revised_plan_id) {
            setRevisedId(d.revised_plan_id);
            if (plan)
              setPlan(await api<CommercePlan>(`${base}/plans/${plan.id}`));
            if (session)
              setSession(
                await api<CommerceSession>(`${base}/sessions/${session.id}`),
              );
            setNotice(
              "Material terms changed. The prior approval cannot authorize the revised plan.",
            );
            if (purchase)
              acceptPurchase(
                await api<CommercePurchase>(`${base}/purchases/${purchase.id}`),
              );
          }
          if (d.session_id && d.plan_id) {
            setSession(
              await api<CommerceSession>(`${base}/sessions/${d.session_id}`),
            );
            await loadPlan(
              await api<CommercePlan>(`${base}/plans/${d.plan_id}`),
            );
            remember(d.session_id);
          }
        } catch {
          setNotice(
            "The request failed and saved state could not be refreshed. Reopen the session to inspect its authoritative backend status.",
          );
        }
      }
    } finally {
      setBusy("");
    }
  }
  async function start() {
    await run("Discovering offers and optimizing landed costs", async () => {
      await acceptResult(
        await api<SessionResult>(
          base + "/sessions",
          manual ? { intent } : { text },
        ),
      );
      setNotice(
        manual
          ? "Explicit structured input used; no AI extraction is claimed."
          : "Gemini interpreted the goal; deterministic services selected offers.",
      );
    });
  }
  async function openSession(id: string) {
    await run("Restoring commerce session", async () => {
      const restored = await api<CommerceSession>(`${base}/sessions/${id}`);
      setSession(restored);
      setIntent(restored.intent);
      setBudget(restored.intent.total_budget || 100000);
      await loadPlan(
        await api<CommercePlan>(`${base}/plans/${restored.latest_plan_id}`),
      );
      await refreshTraces(id);
    });
  }
  async function patch(body: unknown) {
    if (session)
      await run("Merging preferences and replanning", async () => {
        await acceptResult(
          await api<SessionResult>(
            `${base}/sessions/${session.id}/preferences`,
            { expected_version: session.version, ...(body as object) },
          ),
        );
        setNotice(
          "New plan version created. Unchanged requirements were retained. Fresh approval is required.",
        );
      });
  }
  async function createPurchase() {
    if (plan)
      await run("Preparing merchant-specific orders", async () => {
        acceptPurchase(
          await api<CommercePurchase>(base + "/purchases", {
            plan_id: plan.id,
            alternative_index: index,
            idempotency_key: purchaseKey.current,
          }),
        );
        await refreshTraces();
      });
  }
  async function action(name: string, body: unknown = {}) {
    if (!purchase) return;
    await run(`${name} mock purchase`, async () => {
      acceptPurchase(
        name === "refresh"
          ? await api<CommercePurchase>(`${base}/purchases/${purchase.id}`)
          : await api<CommercePurchase>(
              `${base}/purchases/${purchase.id}/${name}`,
              name === "execute"
                ? { idempotency_key: executionKey, simulations: modes }
                : body,
            ),
      );
      await refreshTraces();
    });
  }
  async function retry(id: string) {
    await run("Retrying confirmed merchant failure", async () => {
      const key = retryKeys.current[id] || crypto.randomUUID();
      retryKeys.current[id] = key;
      acceptPurchase(
        await api<CommercePurchase>(`${base}/suborders/${id}/retry`, {
          idempotency_key: key,
          simulation: "success",
        }),
      );
      delete retryKeys.current[id];
      await refreshTraces();
    });
  }
  async function resolve(id: string, outcome: string) {
    if (purchase)
      await run("Recording demo ledger outcome and reconciling", async () => {
        await api(`${base}/demo/attempts/${id}/resolve`, { outcome });
        acceptPurchase(
          await api<CommercePurchase>(
            `${base}/purchases/${purchase.id}/reconcile`,
            {},
          ),
        );
        await refreshTraces();
      });
  }
  const combo = purchase?.snapshot || plan?.result.combinations?.[index],
    valid = plan?.status === "AWAITING_SELECTION" && !revisedId,
    isLatest = session?.latest_plan_id === plan?.id;
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
        <a className="nav-link" href="/setup">
          Setup optimizer
        </a>
        <a className="nav-active" href="/commerce">
          ◈ Commerce intelligence
        </a>
        <div className="history-label">COMMERCE SESSIONS</div>
        <div className="history">
          {history.length ? (
            history.map((id) => (
              <button
                key={id}
                disabled={!!busy}
                onClick={() => openSession(id)}
              >
                ↗ {id.slice(0, 8)}
              </button>
            ))
          ) : (
            <p>No saved sessions yet.</p>
          )}
        </div>
        <div className="sidebar-footer">
          Local mock execution · No real funds
        </div>
      </aside>
      <section className="workspace">
        <header>
          <span>Workspace / Commerce intelligence</span>
          <span className="header-badge">PHASE 03 · DEMO OFFERS</span>
        </header>
        <div className="content">
          <div className="intro">
            <div>
              <p className="eyebrow">
                OFFERS YOU CAN INSPECT. TERMS YOU APPROVE.
              </p>
              <h1>Commerce, with context.</h1>
              <p>
                Compare landed costs, retain preferences, and track every
                merchant outcome.
              </p>
            </div>
          </div>
          <div className="provider-status">
            <span className="live-dot" />
            {providerStatus}
            <small>
              No authorized live merchant or sandbox payment adapter is
              configured.
            </small>
          </div>
          <section className="request-panel">
            <div className="section-title">
              <span className="number">01</span>
              <h2>Research a purchase</h2>
            </div>
            <div className="mode-tabs">
              <button
                disabled={!!busy}
                className={manual ? "secondary" : "primary"}
                onClick={() => setManual(false)}
              >
                Natural language · Gemini
              </button>
              <button
                disabled={!!busy}
                className={manual ? "primary" : "secondary"}
                onClick={() => setManual(true)}
              >
                Explicit structured requirements
              </button>
            </div>
            {manual ? (
              <>
                <label className="budget-input">
                  Budget in INR
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
                  {categories.map((category) => (
                    <label key={category}>
                      <input
                        type="checkbox"
                        checked={intent.items.some(
                          (item) => item.category === category,
                        )}
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
                                    priority: category === "laptop" ? 5 : 3,
                                    hard_constraints: [],
                                    soft_preferences: [],
                                  },
                                ]
                              : intent.items.filter(
                                  (item) => item.category !== category,
                                ),
                          })
                        }
                      />
                      {category}
                    </label>
                  ))}
                </div>
                <p className="demo-note">
                  Structured input bypasses AI extraction; CP-SAT computes the
                  purchase plan.
                </p>
              </>
            ) : (
              <>
                <label htmlFor="commerce-goal" className="sr-only">
                  Commerce purchasing goal
                </label>
                <textarea
                  id="commerce-goal"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
                <p className="demo-note">
                  Gemini interprets requirements and chooses grounded
                  explanation reasons. It cannot authorize payments.
                </p>
              </>
            )}
            <div className="request-bottom">
              <span>Shipping + fees + eligible discounts · Decimal costs</span>
              <button
                className="primary"
                disabled={!!busy || (!manual && text.length < 10)}
                onClick={start}
              >
                Discover offers & optimize ↗
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
                run("Loading revised terms", async () => {
                  const next = await api<CommercePlan>(
                    `${base}/plans/${revisedId}`,
                  );
                  setSession(
                    await api<CommerceSession>(
                      `${base}/sessions/${next.session_id}`,
                    ),
                  );
                  await loadPlan(next);
                  await refreshTraces(next.session_id);
                })
              }
            >
              Review revised plan · Fresh approval required
            </button>
          )}
          {session && plan && (
            <>
              <CommercePlanPanel
                key={plan.id}
                plan={plan}
                combo={combo}
                index={index}
                busy={!!busy}
                disabled={!!busy || !!purchase || !valid || !isLatest}
                onChoose={(i) => {
                  setIndex(i);
                  purchaseKey.current = crypto.randomUUID();
                  setChangeId(
                    plan.result.combinations?.[i]?.items[0]?.offer.id || "",
                  );
                }}
                onPrepare={createPurchase}
                onValidate={() =>
                  run("Revalidating selected terms", async () => {
                    await api(
                      `${base}/plans/${plan.id}/validate?alternative_index=${index}`,
                      {},
                    );
                    setNotice(
                      "Selected quote terms are unchanged. Nothing was silently replaced.",
                    );
                  })
                }
                onRefresh={(ids) =>
                  run("Refreshing demo quotes", async () => {
                    await api(base + "/offers/refresh", { offer_ids: ids });
                    setNotice(
                      "Demo quote timestamps refreshed. Rediscover and replan before approval; no live verification is claimed.",
                    );
                  })
                }
              />
              {plan.status === "INTERRUPTED" && (
                <button
                  className="secondary"
                  disabled={!!busy}
                  onClick={() =>
                    run("Resuming research checkpoint", async () => {
                      const next = await api<CommercePlan>(
                        `${base}/plans/${plan.id}/resume`,
                        {},
                      );
                      setSession(
                        await api<CommerceSession>(
                          `${base}/sessions/${session.id}`,
                        ),
                      );
                      await loadPlan(next);
                      await refreshTraces();
                    })
                  }
                >
                  Resume interrupted research
                </button>
              )}
              {purchase && (
                <MerchantPayments
                  key={purchase.id}
                  purchase={purchase}
                  busy={!!busy}
                  modes={modes}
                  onMode={(id, mode) => setModes({ ...modes, [id]: mode })}
                  onAction={action}
                  onRetry={retry}
                  onResolve={resolve}
                />
              )}
              <section className="replan-controls">
                <h2>Session memory · Change only what you mean</h2>
                <p className="demo-note">
                  Updates merge with this session, preserve unrelated
                  constraints, and never approve revised terms.
                </p>
                <label htmlFor="commerce-update">Preference update</label>
                <textarea
                  id="commerce-update"
                  value={updateText}
                  onChange={(e) => setUpdateText(e.target.value)}
                />
                <div className="cart-controls">
                  <button
                    className="secondary"
                    disabled={!!busy || !isLatest}
                    onClick={() => patch({ text: updateText })}
                  >
                    Merge update with Gemini
                  </button>
                  <button
                    className="secondary"
                    disabled={!!busy || !isLatest}
                    onClick={() =>
                      patch({ patch: { weights: { portability: 5 } } })
                    }
                  >
                    Prefer lighter · Explicit structured update
                  </button>
                </div>
                <div>
                  <label>
                    Revised budget
                    <input
                      type="number"
                      min={1}
                      value={budget}
                      onChange={(e) => setBudget(Number(e.target.value))}
                    />
                  </label>
                  <button
                    className="secondary"
                    disabled={!!busy || !isLatest}
                    onClick={() => patch({ patch: { total_budget: budget } })}
                  >
                    Update budget & replan
                  </button>
                  <button
                    className="secondary"
                    disabled={!!busy || !isLatest}
                    onClick={() =>
                      run("Rediscovering offers", async () =>
                        acceptResult(
                          await api<SessionResult>(
                            `${base}/plans/${plan.id}/replan`,
                            {},
                          ),
                        ),
                      )
                    }
                  >
                    Rediscover & replan
                  </button>
                </div>
                <details>
                  <summary>Relevant conversation</summary>
                  {session.conversation.map((row, i) => (
                    <p key={i}>
                      {row.role}: {row.text}
                    </p>
                  ))}
                </details>
              </section>
              <section className="plan-history">
                <h2>Plan versions & transaction history</h2>
                <p className="demo-note">
                  Open an earlier version to inspect or compensate a partial
                  purchase before creating replacements.
                </p>
                {session.plans.map((row) => (
                  <button
                    className="secondary"
                    disabled={!!busy}
                    key={row.id}
                    onClick={() =>
                      run("Restoring version and transactions", async () =>
                        loadPlan(
                          await api<CommercePlan>(`${base}/plans/${row.id}`),
                        ),
                      )
                    }
                  >
                    Version {row.version} · {row.status}
                  </button>
                ))}
              </section>
              {combo && valid && (
                <details className="demo-simulator">
                  <summary>Demo offer change simulator</summary>
                  <p>
                    Changes local demo records. Revalidation detects revised
                    prices, stock, merchants and expiry.
                  </p>
                  <label>
                    Offer
                    <select
                      value={changeId}
                      onChange={(e) => setChangeId(e.target.value)}
                    >
                      {combo.items.map((row) => (
                        <option key={row.offer.id} value={row.offer.id}>
                          {row.product.model} / {row.offer.merchant_name}
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
                      <option value="price_increase">
                        Base price + INR 4,000
                      </option>
                      <option value="price_decrease">
                        Base price - INR 1,000
                      </option>
                      <option value="out_of_stock">Out of stock</option>
                      <option value="merchant_unavailable">
                        Merchant unavailable
                      </option>
                      <option value="expired">Quote expired</option>
                    </select>
                  </label>
                  <button
                    className="secondary"
                    disabled={!!busy}
                    onClick={() =>
                      run("Changing demo offer", async () => {
                        await api(base + "/demo/offers/change", {
                          offer_id: changeId,
                          change,
                        });
                        setNotice(
                          "Demo terms changed. Check selected terms to produce a revised plan and fresh approval boundary.",
                        );
                      })
                    }
                  >
                    Apply demo offer change
                  </button>
                </details>
              )}
              <details className="trace-panel">
                <summary>Developer trace · Safe structured events</summary>
                <button
                  className="secondary"
                  disabled={!!busy}
                  onClick={() =>
                    run("Refreshing traces", () => refreshTraces())
                  }
                >
                  Refresh traces
                </button>
                <div className="comparison">
                  <table>
                    <thead>
                      <tr>
                        <th>Node / tool</th>
                        <th>State</th>
                        <th>Measurements</th>
                        <th>Recorded</th>
                      </tr>
                    </thead>
                    <tbody>
                      {traces.map((row) => (
                        <tr key={row.id}>
                          <td>
                            {row.node}
                            <small>{row.workflow_id.slice(0, 8)}</small>
                          </td>
                          <td>{row.status}</td>
                          <td>{JSON.stringify(row.details)}</td>
                          <td>{new Date(row.created_at).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="demo-note">
                  No prompts, credentials or payment instruments. Token counts
                  appear only when returned by Gemini.
                </p>
              </details>
            </>
          )}
          <footer>
            <span>IntentOS / Context, offers and explicit authority.</span>
            <span>
              DEMO DISCOVERY · DECIMAL COSTS · RECONCILED MOCK PAYMENTS
            </span>
          </footer>
        </div>
      </section>
    </main>
  );
}
