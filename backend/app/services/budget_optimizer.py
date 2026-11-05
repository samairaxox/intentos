"""Deterministic CP-SAT optimizer. No LLM decisions enter financial arithmetic."""
from collections import Counter
from ortools.sat.python import cp_model
from app.models.multi_schemas import MultiIntent, ItemRequirement
from app.services.optimization import satisfies


def flattened(product: dict) -> dict:
    return {**product.get("specifications", {}), **product}


def matches(product: dict, requirement: ItemRequirement, intent: MultiIntent) -> bool:
    return bool(product.get("category") == requirement.category
                and product.get("available") and product.get("seller_available", True)
                and product.get("stock", 1) > 0
                and product.get("currency") == intent.currency
                and 0 < product.get("price", 0) <= (intent.total_budget or 0)
                and all(satisfies(flattened(product), rule) for rule in requirement.hard_constraints))


def utility(product: dict, requirement: ItemRequirement, intent: MultiIntent, peers: list[dict]) -> int:
    """Integer utility units, normalized components with explicit savings penalty."""
    p = flattened(product)
    best_value = max((q.get("quality_score", q["performance"]) / q["price"] for q in peers), default=1)
    weights = intent.weights.model_dump(exclude={"cost_savings"})
    components = {
        "performance": product["performance"] / 100,
        "quality": product.get("quality_score", product["performance"]) / 100,
        "portability": 1 / (1 + float(p.get("weight_kg", 1))),
        "battery": min(1, float(p.get("battery_hours", 0)) / 24),
        "value": (product.get("quality_score", product["performance"]) / product["price"]) / best_value,
        "preferences": sum(satisfies(p, rule) for rule in requirement.soft_preferences) / len(requirement.soft_preferences) if requirement.soft_preferences else .5,
    }
    # Unknown battery data does not count as a measured zero-hour battery.
    if "battery_hours" not in p: weights["battery"] = 0
    average = sum(max(0, min(1, components[k])) * v for k, v in weights.items()) / (sum(weights.values()) or 1)
    savings = intent.weights.cost_savings + (2 if intent.spending_preference == "savings" else 0)
    if intent.spending_preference == "quality": savings = max(0, savings - 1)
    return round(10000 * requirement.priority * average) - round(10000 * savings * product["price"] / intent.total_budget)


def candidates_for(intent: MultiIntent, products: list[dict]) -> dict[str, list[dict]]:
    # Product IDs must be unique; never treat duplicate provider entries as extra stock.
    unique = {p["id"]: p for p in products}
    return {r.category: sorted((p for p in unique.values() if matches(p, r, intent)), key=lambda p:p["id"]) for r in intent.items}


def summarize(intent: MultiIntent, selected: list[dict], candidates: dict[str, list[dict]]) -> dict:
    counts = Counter(p["id"] for p in selected)
    by_id = {p["id"]:p for p in selected}
    items, spending, total_utility = [], {}, 0
    requirements = {r.category:r for r in intent.items}
    for product_id in sorted(counts):
        p, qty = by_id[product_id], counts[product_id]
        req = requirements[p["category"]]
        score = utility(p, req, intent, candidates[p["category"]])
        line_total = p["price"] * qty
        spending[p["category"]] = spending.get(p["category"], 0) + line_total
        total_utility += score * qty
        items.append({"product":p,"quantity":qty,"unit_price":p["price"],"line_total":line_total,"utility":score*qty,
                      "reason":f"{qty} x {p['name']}; {req.category} priority {req.priority}/5; all hard constraints passed; demo unit price INR {p['price']:,}."})
    total = sum(spending.values())
    omitted = [r.category for r in intent.items if r.category not in spending]
    return {"items":items,"total_cost":total,"remaining_budget":intent.total_budget-total,"utility_score":total_utility,
            "category_spending":spending,"omitted_optional":omitted,
            "tradeoffs":[f"{category}: INR {cost:,} allocated" for category,cost in spending.items()] + [f"Optional {c} omitted to balance utility and savings" for c in omitted]}


def optimize(intent: MultiIntent, products: list[dict], limit: int = 3) -> dict:
    if intent.missing():
        return {"status":"NEEDS_DETAILS","missing_information":intent.missing(),"combinations":[],"candidates":{}}
    candidates = candidates_for(intent, products)
    model = cp_model.CpModel()
    decisions, records, benefits = [], [], []
    for req in intent.items:
        category_vars = []
        for p in candidates[req.category]:
            previous = None
            for unit in range(min(req.quantity, p.get("stock", 1))):
                x = model.new_bool_var(f"{p['id']}:{unit}")
                if previous is not None: model.add(x <= previous)
                previous = x
                decisions.append(x); category_vars.append(x); records.append(p)
                benefits.append(utility(p, req, intent, candidates[req.category]))
        if req.required:
            model.add(sum(category_vars) == req.quantity)
        else:
            included = model.new_bool_var(f"include:{req.category}")
            model.add(sum(category_vars) == req.quantity * included)
    cost = sum(x * p["price"] for x,p in zip(decisions,records))
    objective = sum(x * value for x,value in zip(decisions,benefits))
    model.add(cost <= intent.total_budget)
    combinations = []
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.max_time_in_seconds = 5
    for _ in range(min(limit,3)):
        # Primary utility dominates secondary lower cost. Integer scaling is bounded by schema limits.
        model.maximize(objective * (intent.total_budget + 1) - cost)
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if not combinations:
                return {"status":"INFEASIBLE" if status==cp_model.INFEASIBLE else "SOLVER_LIMIT", "combinations":[],"candidates":candidates}
            break
        selected_flags = [bool(solver.value(x)) for x in decisions]
        chosen = [p for p,flag in zip(records,selected_flags) if flag]
        summary = summarize(intent,chosen,candidates)
        summary["solver_status"] = solver.status_name(status)
        combinations.append(summary)
        # Exact no-good cut; prefix constraints remove symmetry between units of the same SKU.
        model.add_bool_or([~x if flag else x for x,flag in zip(decisions,selected_flags)])
    return {"status":"READY","combinations":combinations,"candidates":candidates}


def cheapest_baseline(intent: MultiIntent, products: list[dict]) -> dict:
    if intent.missing(): return {"status":"NEEDS_DETAILS"}
    candidates = candidates_for(intent, products)
    selected = []
    for req in intent.items:
        if not req.required: continue
        remaining = req.quantity
        for p in sorted(candidates[req.category],key=lambda p:(p["price"],p["id"])):
            count = min(remaining,p.get("stock",1))
            selected.extend([p]*count); remaining -= count
            if not remaining: break
        if remaining: return {"status":"INFEASIBLE"}
    result = summarize(intent,selected,candidates)
    return {"status":"READY" if result["total_cost"]<=intent.total_budget else "INFEASIBLE",**result}
