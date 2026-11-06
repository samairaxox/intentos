import { useState } from "react";
import { CommercePurchase, Simulation, exactMoney } from "@/lib/commerce";
export default function MerchantPayments({
  purchase,
  busy,
  modes,
  onMode,
  onAction,
  onRetry,
  onResolve,
}: {
  purchase: CommercePurchase;
  busy: boolean;
  modes: Record<string, Simulation>;
  onMode: (id: string, mode: Simulation) => void;
  onAction: (action: string, body?: unknown) => void;
  onRetry: (id: string) => void;
  onResolve: (id: string, outcome: string) => void;
}) {
  const [approved, setApproved] = useState(false),
    [pending, setPending] = useState(false);
  return (
    <section className="checkout">
      <div className="section-title">
        <span className="number">02</span>
        <h2>Merchant checkout coordination</h2>
        <span className="tag">{purchase.status}</span>
      </div>
      <p>
        Purchase {purchase.id} · {exactMoney(purchase.amount)}
      </p>
      <p className="demo-note">{purchase.warning}</p>
      <div className="settlement-summary">
        <span>
          Captured: <strong>{exactMoney(purchase.captured_total)}</strong>
        </span>
        <span>
          Mock-refunded: <strong>{exactMoney(purchase.refunded_total)}</strong>
        </span>
      </div>
      {purchase.status === "PENDING_APPROVAL" && (
        <>
          <label className="check">
            <input
              type="checkbox"
              checked={approved}
              onChange={(e) => setApproved(e.target.checked)}
            />
            I explicitly approve every listed product, merchant, quantity and
            quoted amount for this mock purchase.
          </label>
          <button
            className="primary"
            disabled={busy || !approved}
            onClick={() => {
              setApproved(false);
              onAction("approve", { approved: true });
            }}
          >
            Approve complete purchase
          </button>
          <button
            className="secondary cancel"
            disabled={busy}
            onClick={() => onAction("reject")}
          >
            Reject purchase
          </button>
        </>
      )}
      <div className="merchant-orders">
        {purchase.suborders.map((sub) => (
          <article key={sub.id}>
            <div className="workflow-heading">
              <h3>{sub.merchant_name}</h3>
              <span className="tag">{sub.status}</span>
            </div>
            <p>
              {exactMoney(sub.amount)} · {sub.items.length} offer lines
            </p>
            <label>
              Mock provider scenario
              <select
                disabled={busy || !!purchase.execution_key}
                value={modes[sub.merchant_id] || "success"}
                onChange={(e) =>
                  onMode(sub.merchant_id, e.target.value as Simulation)
                }
              >
                <option value="success">Success</option>
                <option value="failure">Definitive payment failure</option>
                <option value="timeout_captured">
                  Timeout, provider captured
                </option>
                <option value="timeout_unknown">
                  Timeout, outcome unknown
                </option>
                <option value="checkout_failure">
                  Merchant checkout failure
                </option>
              </select>
            </label>
            {sub.attempts.map((attempt) => (
              <div className="attempt" key={attempt.id}>
                <span>
                  Attempt {attempt.attempt_number}: {attempt.status}
                </span>
                <small>{attempt.id}</small>
                {attempt.retry_after && (
                  <small>
                    Retry after {new Date(attempt.retry_after).toLocaleString()}
                  </small>
                )}
                {["UNKNOWN", "PROCESSING"].includes(attempt.status) && (
                  <div className="demo-outcome-controls">
                    <span>Demo ledger only:</span>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => onResolve(attempt.id, "CAPTURED")}
                    >
                      Record captured & reconcile
                    </button>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => onResolve(attempt.id, "FAILED")}
                    >
                      Record failed & reconcile
                    </button>
                  </div>
                )}
              </div>
            ))}
            {["FAILED", "CHECKOUT_FAILED"].includes(sub.status) &&
              ![
                "COMPENSATED",
                "COMPENSATION_PENDING",
                "APPROVAL_INVALIDATED",
              ].includes(purchase.status) && (
                <button
                  className="secondary"
                  disabled={busy || purchase.status === "PAYMENT_UNKNOWN"}
                  onClick={() => onRetry(sub.id)}
                >
                  Explicitly retry confirmed failure
                </button>
              )}
          </article>
        ))}
      </div>
      {["APPROVED", "PARTIAL_FAILURE"].includes(purchase.status) &&
        purchase.suborders.some((sub) => sub.status === "AUTHORIZED") && (
          <button
            className="primary"
            disabled={busy}
            onClick={() => onAction("execute")}
          >
            {purchase.execution_key
              ? "Resume remaining authorized checkouts"
              : "Execute mock merchant checkouts"}
          </button>
        )}
      {["PAYMENT_UNKNOWN", "EXECUTING", "COMPENSATION_PENDING"].includes(
        purchase.status,
      ) && (
        <button
          className="primary"
          disabled={busy}
          onClick={() => onAction("reconcile")}
        >
          Reconcile provider outcome · No charge retry
        </button>
      )}
      {[
        "PARTIAL_FAILURE",
        "PAID",
        "COMPENSATION_PENDING",
        "COMPENSATED",
      ].includes(purchase.status) && (
        <div className="compensation-controls">
          <label className="check">
            <input
              type="checkbox"
              checked={pending}
              onChange={(e) => setPending(e.target.checked)}
            />
            Simulate compensation pending
          </label>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => onAction("compensate", { pending })}
          >
            Request mock compensation
          </button>
          <p className="demo-note">
            Mock reversals are recorded individually. Real refunds are not
            integrated or guaranteed.
          </p>
        </div>
      )}
      <p className="demo-note">
        Execution action: {purchase.workflow.action_required || purchase.status}
        . A timeout is never blindly retried.
      </p>
      <button
        className="secondary"
        disabled={busy}
        onClick={() => onAction("refresh")}
      >
        Refresh transaction state
      </button>
    </section>
  );
}
