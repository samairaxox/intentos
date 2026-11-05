from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from app.models.multi_schemas import MultiIntent
from app.services.budget_optimizer import candidates_for, optimize

class MultiState(TypedDict, total=False):
    text: str
    intent: dict
    products: list[dict]
    candidates: dict[str, list[dict]]
    result: dict
    status: str
    steps: list[str]
    selected_index: int
    selection: dict
    awaiting_selection: bool


def planning_graph(ai, provider):
    def parse(s):
        intent = MultiIntent.model_validate(s["intent"]) if "intent" in s else ai.parse_multi(s["text"])
        return {"intent":intent.model_dump(),"steps":["Parse Multi-Product Intent"]}
    def validate(s):
        intent = MultiIntent.model_validate(s["intent"])
        missing = intent.missing()
        return {"status":"NEEDS_DETAILS" if missing else "VALID", "result":{"missing_information":missing},"steps":s["steps"]+["Validate Requirements"]}
    def discover(s):
        return {"products":provider.discover([r["category"] for r in s["intent"]["items"]]),"steps":s["steps"]+["Discover Products"]}
    def filter_products(s):
        return {"candidates":candidates_for(MultiIntent.model_validate(s["intent"]),s["products"]),"steps":s["steps"]+["Filter Eligible Products"]}
    def optimize_budget(s):
        result = optimize(MultiIntent.model_validate(s["intent"]),s["products"])
        return {"result":result,"status":result["status"],"steps":s["steps"]+["Optimize Budget"]}
    def evaluate(s):
        for combination in s["result"].get("combinations",[]):
            if combination["total_cost"]>s["intent"]["total_budget"]:
                raise ValueError("Optimizer returned an over-budget combination")
        return {"steps":s["steps"]+["Evaluate Purchase Plan"]}
    def explain(s):
        # Explanations reference only server-computed amounts and catalog facts.
        return {"steps":s["steps"]+["Explain Decisions"]}
    def await_selection(s):
        return {"awaiting_selection":s["status"]=="READY", "steps":s["steps"]+["Await User Selection"]}
    def checkout(s):
        combinations = s["result"]["combinations"]
        index = s["selected_index"]
        if index < 0 or index >= len(combinations): raise ValueError("Unknown plan alternative")
        return {"selection":combinations[index],"awaiting_selection":False,"steps":s["steps"]+["Prepare Checkout"]}
    graph=StateGraph(MultiState)
    for name,fn in {"parse":parse,"validate":validate,"discover":discover,"filter":filter_products,"optimize":optimize_budget,"evaluate":evaluate,"explain":explain,"await":await_selection,"checkout":checkout}.items(): graph.add_node(name,fn)
    graph.add_edge(START,"parse");graph.add_edge("parse","validate")
    graph.add_conditional_edges("validate",lambda s:"stop" if s["status"]=="NEEDS_DETAILS" else "continue",{"stop":END,"continue":"discover"})
    for a,b in [("discover","filter"),("filter","optimize"),("optimize","evaluate"),("evaluate","explain"),("explain","await")]: graph.add_edge(a,b)
    graph.add_conditional_edges("await",lambda s:"checkout" if "selected_index" in s and s["status"]=="READY" else "stop",{"checkout":"checkout","stop":END})
    graph.add_edge("checkout",END)
    return graph.compile()


def checkout_graph():
    """Resume persisted state at explicit selection, without reparsing or silently optimizing."""
    def select(s):
        index=s["selected_index"]
        if index>=len(s["result"].get("combinations",[])): raise ValueError("Unknown alternative")
        return {"selection":s["result"]["combinations"][index],"awaiting_selection":False,"steps":s["steps"]+["Prepare Checkout"]}
    graph=StateGraph(MultiState)
    graph.add_node("checkout",select);graph.add_edge(START,"checkout");graph.add_edge("checkout",END)
    return graph.compile()
