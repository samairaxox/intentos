"use client";
import { useEffect, useState } from "react";
import { api, Analysis, Order, Payment, AuditEvent, money } from "@/lib/api";
import RecommendationCard from "@/components/RecommendationCard";

const steps = [
  "Intent Parser",
  "Intent Validator",
  "Product Discovery",
  "Constraint Filter",
  "Ranking Engine",
  "Explanation Generator",
];
export default function Home() {
  const [text, setText] = useState(
    "Find me the best laptop under ₹75,000 for coding and AI development. Intel processor, at least 16 GB RAM, lightweight, and good battery life.",
  );
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [payment, setPayment] = useState<Payment | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [approve, setApprove] = useState(false);
  const [failure, setFailure] = useState(false);
  const [paymentKey, setPaymentKey] = useState("");
  const [compare, setCompare] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  useEffect(() => {
    try {
      setHistory(JSON.parse(localStorage.getItem("intentos-orders") || "[]"));
    } catch {
      setHistory([]);
    }
  }, []);
  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy("");
    }
  }
  async function refresh(id: string) {
    const [o, e] = await Promise.all([
      api<Order>(`/api/v1/orders/${id}`),
      api<AuditEvent[]>(`/api/v1/orders/${id}/events`),
    ]);
    setOrder(o);
    setEvents(e);
    setPayment(o.payment || null);
  }
  function remember(id: string) {
    setHistory((previous) => {
      const next = [id, ...previous.filter((v) => v !== id)].slice(0, 20);
      localStorage.setItem("intentos-orders", JSON.stringify(next));
      return next;
    });
  }
  async function analyze() {
    await run("Analyzing your request", async () => {
      setAnalysis(null);
      setOrder(null);
      setPayment(null);
      setEvents([]);
      setApprove(false);
      setAnalysis(await api<Analysis>("/api/v1/purchases/analyze", { text }));
    });
  }
  async function select(product_id: string) {
    if (!analysis) return;
    await run("Preparing checkout", async () => {
      const o = await api<Order>("/api/v1/orders", {
        session_id: analysis.id,
        product_id,
        idempotency_key: crypto.randomUUID(),
      });
      setPayment(null);
      setApprove(false);
      setFailure(false);
      setPaymentKey(crypto.randomUUID());
      remember(o.id);
      await refresh(o.id);
    });
  }
  async function approveOrder() {
    if (!order || !approve) return;
    await run("Recording approval", async () => {
      await api(`/api/v1/orders/${order.id}/approve`, { approved: true });
      await refresh(order.id);
    });
  }
  async function pay() {
    if (!order) return;
    await run("Processing simulated payment", async () => {
      setPayment(
        await api<Payment>(`/api/v1/orders/${order.id}/pay`, {
          idempotency_key: paymentKey,
          simulate_failure: failure,
        }),
      );
      await refresh(order.id);
    });
  }
  return (
    <main>
      <aside>
        <a className="brand" href="/">
          i<span>IntentOS</span>
          <sup>β</sup>
        </a>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <div className="nav-active">
          ◈ <span>Purchase agent</span>
          <span className="nav-dot" />
        </div>
        <a className="nav-link" href="/setup">
          Multi-product setup optimizer ↗
        </a>
        <div className="history-label">RECENT ORDERS</div>
        <div className="history">
          {history.length === 0 ? (
            <p>Your orders will appear here.</p>
          ) : (
            history.map((id) => (
              <button
                key={id}
                disabled={!!busy}
                onClick={() =>
                  run("Loading order", async () => {
                    setAnalysis(null);
                    setPayment(null);
                    setApprove(false);
                    setPaymentKey(crypto.randomUUID());
                    await refresh(id);
                  })
                }
              >
                ↗ {id.slice(0, 8)}
              </button>
            ))
          )}
        </div>
        <div className="sidebar-footer">
          <span className="live-dot" /> Local demo environment
          <p>No real funds. You stay in control.</p>
        </div>
      </aside>
      <section className="workspace">
        <header>
          <span>
            Workspace <span className="slash">/</span> Purchase agent
          </span>
          <span className="header-badge">MOCK PAYMENTS ONLY</span>
        </header>
        <div className="content">
          <div className="intro">
            <div>
              <p className="eyebrow">INTELLIGENCE, WITH INTENTION</p>
              <h1>A better way to buy.</h1>
              <p>
                Tell us what you need. Your agent does the comparison.
                <br />
                Every purchase stays yours to approve.
              </p>
            </div>
            <div className="version">
              PHASE 01<span>Agentic commerce</span>
            </div>
          </div>
          <section className="request-panel">
            <div className="section-title">
              <span className="number">01</span>
              <h2>What are you looking for?</h2>
              <span className="tag neutral">LAPTOPS · INR</span>
            </div>
            <label className="sr-only" htmlFor="request">
              Purchasing goal
            </label>
            <textarea
              id="request"
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={!!busy}
              minLength={10}
              maxLength={4000}
            />
            <div className="request-bottom">
              <span>
                ✧ Powered by Gemini · Structured intent, deterministic decisions
              </span>
              <button
                className="primary"
                disabled={!!busy || text.trim().length < 10}
                onClick={analyze}
              >
                {busy === "Analyzing your request"
                  ? "Analyzing…"
                  : "Find my best match"}{" "}
                <span>↗</span>
              </button>
            </div>
          </section>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {busy && (
            <p className="loading" role="status">
              <span className="live-dot" />
              {busy}…
            </p>
          )}
          <section className="workflow">
            <div className="workflow-heading">
              <h2>Agent workflow</h2>
              <span>
                {analysis
                  ? analysis.status.replaceAll("_", " ")
                  : busy === "Analyzing your request"
                    ? "RUNNING"
                    : "READY WHEN YOU ARE"}
              </span>
            </div>
            <div className="steps">
              {steps.map((step, i) => (
                <div
                  key={step}
                  className={analysis?.steps.includes(step) ? "done" : ""}
                >
                  <span>
                    {analysis?.steps.includes(step)
                      ? "✓"
                      : String(i + 1).padStart(2, "0")}
                  </span>
                  {step}
                </div>
              ))}
            </div>
            <p>
              Completed stages are shown from the backend result. Analysis runs
              as one request.
            </p>
          </section>
          {analysis && (
            <section className="intent-summary">
              <h2>Understood requirements</h2>
              <p>
                Maximum budget:{" "}
                {analysis.intent.max_budget
                  ? money(analysis.intent.max_budget)
                  : "Please specify"}{" "}
                {analysis.intent.currency}
              </p>
              <p>Use case: {analysis.intent.use_case || "Not specified"}</p>
              <div className="checkout-grid">
                <div>
                  <h3>Mandatory constraints</h3>
                  {[
                    ...analysis.intent.required_specifications,
                    ...analysis.intent.hard_constraints,
                  ].map((rule, index) => (
                    <p key={index}>
                      {rule.field.replaceAll("_", " ")} {rule.operator}{" "}
                      {rule.value}
                    </p>
                  ))}
                </div>
                <div>
                  <h3>Soft preferences</h3>
                  {[
                    ...analysis.intent.preferred_specifications,
                    ...analysis.intent.soft_preferences,
                  ].map((rule, index) => (
                    <p key={index}>
                      {rule.field.replaceAll("_", " ")} {rule.operator}{" "}
                      {rule.value}
                    </p>
                  ))}
                </div>
              </div>
              <p className="demo-note">
                Review the extracted intent. If anything is missing or
                misunderstood, update your request and analyze again before
                creating an order.
              </p>
            </section>
          )}
          {analysis?.status === "NEEDS_DETAILS" && (
            <div className="notice">
              Please clarify:{" "}
              {analysis.intent.missing_essential_details.join(", ")}. Update
              your request and try again.
            </div>
          )}
          {analysis?.status === "NO_MATCH" && (
            <div className="notice">
              No demo products meet all mandatory constraints. Adjust your
              requirements and try again.
            </div>
          )}
          {!!analysis?.recommendations?.length && (
            <section>
              <div className="results-heading">
                <div>
                  <p className="eyebrow">YOUR SHORTLIST</p>
                  <h2>Good choices. Clear trade-offs.</h2>
                </div>
                <button
                  className="secondary"
                  onClick={() => setCompare(!compare)}
                >
                  {compare ? "Hide comparison" : "Compare products"}
                </button>
              </div>
              <p className="demo-note">
                Sample configurations and prices · No live merchant verification
                · AI explanations may contain errors; review specifications.
              </p>
              <div className="products">
                {analysis.recommendations.map((item, index) => (
                  <RecommendationCard
                    key={item.product.id}
                    item={item}
                    index={index}
                    disabled={!!busy}
                    onSelect={() => select(item.product.id)}
                  />
                ))}
              </div>
              {compare && (
                <div className="comparison">
                  <table>
                    <caption>Catalog specification comparison</caption>
                    <thead>
                      <tr>
                        <th>Specification</th>
                        {analysis.recommendations.map((r) => (
                          <th key={r.product.id}>{r.product.name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(
                        [
                          "processor",
                          "ram_gb",
                          "storage_gb",
                          "weight_kg",
                          "battery_hours",
                        ] as const
                      ).map((key) => (
                        <tr key={key}>
                          <th>{key.replaceAll("_", " ")}</th>
                          {analysis.recommendations!.map((r) => (
                            <td key={r.product.id}>{r.product[key]}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
          {order && (
            <section className="checkout">
              <div className="section-title">
                <span className="number">02</span>
                <h2>Review & authorize</h2>
                <span className="tag">{order.status.replaceAll("_", " ")}</span>
              </div>
              <div className="checkout-grid">
                <div>
                  <p className="eyebrow">ORDER {order.id.slice(0, 8)}</p>
                  <h3>
                    {analysis?.recommendations?.find(
                      (r) => r.product.id === order.product_id,
                    )?.product.name || order.product_id}
                  </h3>
                  <p className="price">{money(order.amount)}</p>
                  <p className="demo-note">
                    Server-verified demo amount. No real money is transferred.
                  </p>
                  {order.status === "PENDING_APPROVAL" && (
                    <>
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={approve}
                          onChange={(e) => setApprove(e.target.checked)}
                        />
                        I explicitly approve this product and amount for a
                        simulated purchase.
                      </label>
                      <button
                        className="primary"
                        disabled={!approve || !!busy}
                        onClick={approveOrder}
                      >
                        Approve order
                      </button>
                    </>
                  )}
                  {order.status === "APPROVED" && (
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
                        onClick={pay}
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
                          await refresh(order.id);
                        })
                      }
                    >
                      Cancel order
                    </button>
                  )}
                  {payment && (
                    <div className="notice" role="status">
                      {payment.status === "PAID"
                        ? "Simulated payment completed."
                        : "Simulated payment failed. No funds moved. Create a new order to try again."}
                      <p>Transaction: {payment.id}</p>
                    </div>
                  )}
                </div>
                <div className="audit">
                  <h3>Transaction history</h3>
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
                  <button
                    className="secondary"
                    disabled={!!busy}
                    onClick={() =>
                      run("Refreshing order", () => refresh(order.id))
                    }
                  >
                    Refresh status
                  </button>
                </div>
              </div>
            </section>
          )}
          <footer>
            <span>IntentOS / Designed for deliberate decisions.</span>
            <span>DEMO DATA · HUMAN APPROVAL · MOCK GATEWAY</span>
          </footer>
        </div>
      </section>
    </main>
  );
}
