import { useState } from "react";
import { CommercePlan, CommerceCombination, exactMoney } from "@/lib/commerce";
import OfferComparison from "./OfferComparison";
export default function CommercePlanPanel({
  plan,
  combo,
  index,
  disabled,
  busy,
  onChoose,
  onPrepare,
  onValidate,
  onRefresh,
}: {
  plan: CommercePlan;
  combo: CommerceCombination | undefined;
  index: number;
  disabled: boolean;
  busy: boolean;
  onChoose: (i: number) => void;
  onPrepare: () => void;
  onValidate: () => void;
  onRefresh: (ids: string[]) => void;
}) {
  const offers = plan.result.offers || [];
  const products = Array.from(
    new Map(offers.map((row) => [row.product.id, row.product])).values(),
  );
  const [chosen, setChosen] = useState("");
  const comparing = offers.filter(
    (row) =>
      row.product.id ===
      (chosen || combo?.items[0]?.product.id || products[0]?.id),
  );
  return (
    <>
      <section className="intent-summary">
        <div className="workflow-heading">
          <h2>Research · Plan version {plan.version}</h2>
          <span>{plan.status}</span>
        </div>
        <p>Budget: INR {plan.intent.total_budget || "Missing"}</p>
        <div className="requirement-tags">
          {(plan.intent.items || []).map((item) => (
            <div key={item.category}>
              <strong>
                {item.quantity} × {item.category}
              </strong>
              <span>
                {item.required ? "Required" : "Optional"} · Priority{" "}
                {item.priority}/5
              </span>
              {item.hard_constraints.map((r, i) => (
                <small key={i}>
                  Must: {r.field} {r.operator} {String(r.value)}
                </small>
              ))}
              {item.soft_preferences.map((r, i) => (
                <small key={i}>
                  Prefer: {r.field} {r.operator} {String(r.value)}
                </small>
              ))}
            </div>
          ))}
        </div>
        <p className="demo-note">
          Completed stages: {plan.workflow.completed?.join(" → ")}
        </p>
        <p className="demo-note">
          Soft weights:{" "}
          {Object.entries(plan.intent.weights || {})
            .map(([key, value]) => `${key}: ${value}`)
            .join(" · ")}
        </p>
      </section>
      {plan.changes.length > 0 && (
        <div className="notice">
          {plan.changes.map((text, i) => (
            <p key={i}>{text}</p>
          ))}
        </div>
      )}
      {plan.result.missing_information?.length ? (
        <div className="notice">
          Please clarify: {plan.result.missing_information.join(", ")}
        </div>
      ) : null}
      {["NO_MATCH", "STALE_OFFERS", "NO_PRODUCTS", "SOLVER_LIMIT"].includes(
        plan.status,
      ) && (
        <div className="notice">
          No checkout-ready plan: {plan.status}. Refresh eligible demo quotes or
          revise requirements.
        </div>
      )}
      <div className="alternative-plans">
        {plan.result.combinations?.map((row, i) => (
          <button
            disabled={disabled}
            className={i === index ? "selected-plan" : "secondary"}
            key={i}
            onClick={() => onChoose(i)}
          >
            <strong>{i === 0 ? "Best utility" : `Alternative ${i}`}</strong>
            <span>{exactMoney(row.total)}</span>
            <small>
              {row.utility_score} utility · {row.solver_status}
            </small>
          </button>
        ))}
      </div>
      {combo && (
        <>
          <section className="allocation">
            <div className="allocation-header">
              <div>
                <p className="eyebrow">ESTIMATED TOTAL · KNOWN COMPONENTS</p>
                <h2>{exactMoney(combo.total)}</h2>
              </div>
              <div>
                <strong>{exactMoney(combo.remaining_budget)}</strong>
                <p>remaining</p>
              </div>
            </div>
            <div
              className="allocation-bar"
              role="img"
              aria-label="Merchant cost allocation"
            >
              {combo.merchant_allocation?.map((row, i) => (
                <span
                  key={row.merchant_id}
                  title={`${row.merchant_id}: ${exactMoney(row.amount)}`}
                  style={{
                    width: row.share_percent + "%",
                    background: ["#276b4f", "#7d9a6a", "#b8b08e"][i % 3],
                  }}
                />
              ))}
            </div>
            <div className="allocation-legend">
              {Object.entries(combo.merchant_totals).map(([id, total]) => (
                <span key={id}>
                  {id}: {exactMoney(total)}
                </span>
              ))}
            </div>
            <dl className="commerce-breakdown">
              {Object.entries(combo.cost_breakdown).map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd>{exactMoney(value)}</dd>
                </div>
              ))}
            </dl>
            <p className="demo-note">
              {combo.explanation} Taxes are included only when supported.
              Shipping and fees are per unit. No potential coupon or basket
              threshold is assumed.
            </p>
          </section>
          <div className="setup-cart">
            {combo.items.map((row) => (
              <article className="setup-line" key={row.offer.id}>
                <div className="category-icon">
                  {row.product.category[0].toUpperCase()}
                </div>
                <div className="line-description">
                  <p className="eyebrow">
                    {row.quantity} × {row.product.category} ·{" "}
                    {row.freshness.label}
                  </p>
                  <h3>{row.product.name}</h3>
                  <p>{row.offer.merchant_name}</p>
                  <p className="demo-note">{row.reason}</p>
                  <details>
                    <summary>Specifications and quote</summary>
                    <p>{JSON.stringify(row.product.specifications)}</p>
                    <p>
                      Unit cost {exactMoney(row.pricing.final_price)} · Valid
                      until{" "}
                      {new Date(row.freshness.valid_until).toLocaleString()}
                    </p>
                  </details>
                </div>
                <strong>{exactMoney(row.line_total)}</strong>
              </article>
            ))}
          </div>
          <div className="cart-controls">
            <button className="primary" disabled={disabled} onClick={onPrepare}>
              Prepare merchant suborders
            </button>
            <button
              className="secondary"
              disabled={busy || plan.status !== "AWAITING_SELECTION"}
              onClick={onValidate}
            >
              Check selected terms
            </button>
          </div>
        </>
      )}
      {products.length > 0 && (
        <section className="offer-comparison">
          <h2>Compare merchant offers</h2>
          <label>
            Underlying product
            <select
              disabled={busy}
              value={chosen || comparing[0]?.product.id || ""}
              onChange={(e) => setChosen(e.target.value)}
            >
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <OfferComparison offers={comparing} />
          <button
            className="secondary"
            onClick={() => onRefresh(comparing.map((row) => row.offer.id))}
          >
            Refresh these demo quotes
          </button>
        </section>
      )}
    </>
  );
}
