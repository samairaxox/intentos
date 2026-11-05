import { Combination, MultiProduct } from "@/lib/multi";
import { money } from "@/lib/api";
export default function PlanCart({
  combination,
  candidates,
  editable,
  busy,
  onReplace,
  onRemove,
}: {
  combination: Combination;
  candidates: Record<string, MultiProduct[]>;
  editable: boolean;
  busy: boolean;
  onReplace: (id: string, replacement: string) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <div className="setup-cart">
      {combination.items.map((line) => (
        <article className="setup-line" key={line.product.id}>
          <div className="category-icon" aria-hidden="true">
            {line.product.category.slice(0, 1).toUpperCase()}
          </div>
          <div className="line-description">
            <p className="eyebrow">
              {line.product.category} · QTY {line.quantity}
            </p>
            <h3>{line.product.name}</h3>
            <p>{line.product.seller}</p>
            <p className="demo-note">{line.reason}</p>
            <details>
              <summary>Catalog specifications</summary>
              <dl>
                {Object.entries(line.product.specifications).map(
                  ([key, value]) => (
                    <div key={key}>
                      <dt>{key.replaceAll("_", " ")}</dt>
                      <dd>{String(value)}</dd>
                    </div>
                  ),
                )}
              </dl>
              <p>Demo record: {line.product.timestamp.slice(0, 10)}</p>
            </details>
            {editable && (
              <div className="line-actions">
                <label>
                  Replace with an eligible product
                  <select
                    aria-label={`Replace ${line.product.name}`}
                    disabled={busy}
                    value={line.product.id}
                    onChange={(e) => onReplace(line.product.id, e.target.value)}
                  >
                    {(candidates[line.product.category] || []).map(
                      (product) => (
                        <option key={product.id} value={product.id}>
                          {product.model} · {money(product.price)}
                        </option>
                      ),
                    )}
                  </select>
                </label>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => onRemove(line.product.id)}
                >
                  Remove
                </button>
              </div>
            )}
          </div>
          <strong>{money(line.line_total)}</strong>
        </article>
      ))}
    </div>
  );
}
