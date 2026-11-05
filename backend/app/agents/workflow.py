from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from app.models.schemas import Intent
from app.services.optimization import eligible, rank

class WorkflowState(TypedDict, total=False):
    text: str
    intent: dict
    products: list[dict]
    eligible: list[dict]
    recommendations: list[dict]
    status: str
    steps: list[str]

def build_workflow(ai, provider):
    def parsed(s):
        return {"intent":ai.parse(s["text"]).model_dump(), "steps":["Intent Parser"]}
    def validated(s):
        intent = Intent.model_validate(s["intent"])
        missing = list(intent.missing_essential_details)
        if intent.max_budget is None: missing.append("maximum budget")
        if intent.category.casefold() != "laptop": missing.append("supported category: laptop")
        if intent.currency != "INR": missing.append("supported currency: INR")
        return {"status":"NEEDS_DETAILS" if missing else "VALID", "intent":{**s["intent"], "missing_essential_details":list(dict.fromkeys(missing))},"steps":s["steps"]+["Intent Validator"]}
    def discovered(s):
        return {"products":provider.discover(),"steps":s["steps"]+["Product Discovery"]}
    def filtered(s):
        intent = Intent.model_validate(s["intent"])
        return {"eligible":[p for p in s["products"] if eligible(p,intent)], "steps":s["steps"]+["Constraint Filter"]}
    def ranked(s):
        recs = rank(s["eligible"], Intent.model_validate(s["intent"]))[:3]
        return {"recommendations":recs,"status":"READY" if recs else "NO_MATCH", "steps":s["steps"]+["Ranking Engine"]}
    def explained(s):
        explanations = ai.explain(s["recommendations"])
        return {"recommendations":[{**r,"explanation":explanations[r["product"]["id"]]} for r in s["recommendations"]],"steps":s["steps"]+["Explanation Generator"]}
    graph = StateGraph(WorkflowState)
    nodes = {"parser":parsed,"validator":validated,"discovery":discovered,"filter":filtered,"ranking":ranked,"explanation":explained}
    for name,fn in nodes.items(): graph.add_node(name,fn)
    graph.add_edge(START,"parser")
    graph.add_edge("parser","validator")
    graph.add_conditional_edges("validator",lambda s: "stop" if s["status"]=="NEEDS_DETAILS" else "continue",{"stop":END,"continue":"discovery"})
    for a,b in [("discovery","filter"),("filter","ranking"),("ranking","explanation")]: graph.add_edge(a,b)
    graph.add_edge("explanation",END)
    return graph.compile()
