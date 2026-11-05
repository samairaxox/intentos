from app.models.schemas import Intent, Constraint

def satisfies(product: dict, rule: Constraint) -> bool:
    actual = product.get(rule.field)
    if actual is None:
        return False
    if rule.operator == "eq":
        return str(actual).casefold() == str(rule.value).casefold()
    try:
        a, b = float(actual), float(rule.value)
        return a >= b if rule.operator == "min" else a <= b
    except (TypeError, ValueError):
        return False

def eligible(product: dict, intent: Intent) -> bool:
    return bool(product["available"] and intent.max_budget is not None
                and product["currency"] == intent.currency
                and product["price"] <= intent.max_budget
                and all(satisfies(product, r) for r in intent.required_specifications + intent.hard_constraints))

def rank(products: list[dict], intent: Intent) -> list[dict]:
    results = []
    preferences = intent.preferred_specifications + intent.soft_preferences
    technical = any(word in intent.use_case.casefold() for word in ("coding", "development", "ai", "gaming", "engineering"))
    weights = {"performance":.4 if technical else .3,"value":.2,"portability":.1 if technical else .15,"battery":.1 if technical else .15,"preferences":.2}
    for p in products:
        scores = {
            "performance": min(p["performance"] / 100, 1),
            "value": max(0, 1 - p["price"] / intent.max_budget),
            "portability": max(0, min(1, (3 - p["weight_kg"]) / 2)),
            "battery": min(p["battery_hours"] / 15, 1),
            "preferences": sum(satisfies(p, r) for r in preferences) / len(preferences) if preferences else .5,
        }
        score = sum(scores[k] * w for k, w in weights.items())
        results.append({"product":p,"score":round(score*100,2),"breakdown":scores,
                        "tradeoffs":[f"Weight: {p['weight_kg']} kg", f"Catalog battery estimate: {p['battery_hours']} hours"]})
    return sorted(results, key=lambda r: (-r["score"], r["product"]["price"], r["product"]["id"]))
