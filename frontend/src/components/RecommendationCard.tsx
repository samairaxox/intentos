import { Recommendation, money } from "@/lib/api";
export default function RecommendationCard({
  item,
  index,
  disabled,
  onSelect,
}: {
  item: Recommendation;
  index: number;
  disabled: boolean;
  onSelect: () => void;
}) {
  const p = item.product;
  return (
    <article className="product-card">
      <div className="card-top">
        <span className="tag">
          {index === 0 ? "TOP MATCH" : `OPTION 0${index + 1}`}
        </span>
        <span className="score">
          {item.score.toFixed(1)}
          <small>/100</small>
        </span>
      </div>
      <div className="laptop" aria-hidden="true">
        <div />
        <span />
      </div>
      <p className="eyebrow">DEMO CATALOG · {p.processor_brand}</p>
      <h3>{p.name}</h3>
      <p className="price">{money(p.price)}</p>
      <dl className="specs">
        <div>
          <dt>Memory</dt>
          <dd>{p.ram_gb} GB</dd>
        </div>
        <div>
          <dt>Storage</dt>
          <dd>{p.storage_gb} GB</dd>
        </div>
        <div>
          <dt>Weight</dt>
          <dd>{p.weight_kg} kg</dd>
        </div>
        <div>
          <dt>Battery estimate</dt>
          <dd>{p.battery_hours} hrs</dd>
        </div>
      </dl>
      <p className="explanation">{item.explanation}</p>
      <details>
        <summary>Scoring & trade-offs</summary>
        {Object.entries(item.breakdown).map(([key, value]) => (
          <p key={key}>
            {key}: {(value * 100).toFixed(0)} / 100
          </p>
        ))}
        {item.tradeoffs.map((t) => (
          <p key={t}>{t}</p>
        ))}
        <p>
          {p.seller} · Sample as of {p.timestamp.slice(0, 10)}
        </p>
      </details>
      <button disabled={disabled} onClick={onSelect}>
        Select & review <span>↗</span>
      </button>
    </article>
  );
}
