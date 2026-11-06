import { OfferView, exactMoney } from "@/lib/commerce";
export default function OfferComparison({ offers }: { offers: OfferView[] }) {
  return (
    <div className="comparison">
      <table>
        <caption>
          Merchant quotes · costs and provenance supplied by the backend
        </caption>
        <thead>
          <tr>
            <th>Merchant / source</th>
            <th>Base</th>
            <th>Delivery / fees</th>
            <th>Confirmed discount</th>
            <th>Potential, not applied</th>
            <th>Estimated final</th>
            <th>Freshness</th>
          </tr>
        </thead>
        <tbody>
          {offers.map((view) => (
            <tr key={view.offer.id}>
              <td>
                <strong>{view.offer.merchant_name}</strong>
                <small>
                  {view.freshness.label} · {view.offer.verification_status}
                </small>
              </td>
              <td>{exactMoney(view.pricing.base_price)}</td>
              <td>
                {exactMoney(view.pricing.shipping)} /{" "}
                {exactMoney(view.pricing.fees)}
              </td>
              <td>{exactMoney(view.pricing.confirmed_discount)}</td>
              <td>
                {view.pricing.potential_discounts.map((d, i) => (
                  <p key={i}>
                    {d.label}: {exactMoney(d.amount)}
                  </p>
                ))}
              </td>
              <td>
                {exactMoney(view.pricing.final_price)}
                <small>
                  {view.pricing.taxes_supported
                    ? "Supported tax estimate included"
                    : "Tax not supplied; not assumed tax-free"}
                </small>
              </td>
              <td>
                {view.freshness.reason}
                <small>
                  Retrieved {new Date(view.offer.retrieved_at).toLocaleString()}
                </small>
                <small>
                  Valid until{" "}
                  {new Date(view.freshness.valid_until).toLocaleString()}
                </small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
