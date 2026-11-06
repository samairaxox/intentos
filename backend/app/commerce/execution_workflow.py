from time import perf_counter
from typing import TypedDict
from langgraph.graph import StateGraph,START,END
from app.commerce.schemas import ExecuteRequest
from app.commerce.payments import PaymentAuthorizationService,PaymentExecutionService,purchase_for,suborders,aggregate
from app.commerce.sessions import ensure_current
from app.commerce.tracing import TraceRecorder

class ExecutionState(TypedDict,total=False):
    purchase_id:str
    request:dict
    status:str
    completed:list[str]
    merchant_outcomes:dict[str,str]
    action_required:str | None


def execute_checkout_graph(db,purchase_id,request,ai):
    purchase,plan=purchase_for(db,purchase_id)
    trace=TraceRecorder(db,plan.id,plan.session_id)
    def approval(s):
        if purchase.status=='REJECTED':return {'status':'REJECTED','action_required':'NEW_EXPLICIT_SELECTION'}
        PaymentAuthorizationService().verify(db,purchase)
        return {'status':purchase.status}
    def revalidate(s):
        # Replaying a terminal result does not start a new checkout or require a fresh market quote.
        if purchase.status not in ['PAID','COMPENSATED','COMPENSATION_PENDING','PAYMENT_FAILED']:
            ensure_current(db,plan,purchase.snapshot,ai)
        return {'status':purchase.status}
    def execute(s):
        result=PaymentExecutionService().execute(db,purchase_id,ExecuteRequest.model_validate(s['request']),ai)
        return {'status':result.status}
    def verify(s):
        db.refresh(purchase);aggregate(db,purchase)
        return {'status':purchase.status,'merchant_outcomes':{sub.merchant_id:sub.status for sub in suborders(db,purchase)},'action_required':None if purchase.status=='PAID' else 'REVIEW_OUTCOME'}
    def reconciliation(s):return {'action_required':'RECONCILE_WITH_PROVIDER_BEFORE_RETRY'}
    def failure(s):return {'action_required':'REVIEW_PARTIAL_OUTCOME_OR_EXPLICITLY_RETRY_CONFIRMED_FAILURE'}
    graph=StateGraph(ExecutionState)
    for name,fn in {'await_user_approval':approval,'revalidate_offers':revalidate,'execute_authorized_checkout':execute,'verify_result':verify,'await_reconciliation':reconciliation,'report_checkout_or_payment_failure':failure}.items():
        def wrapped(s,name=name,fn=fn):
            started=perf_counter()
            try:
                result=fn(s);result['completed']=s.get('completed',[])+[name]
                purchase.workflow={**s,**result}
                trace.record(name,result.get('status',s.get('status','COMPLETED')),{'duration_ms':round((perf_counter()-started)*1000,3),'purchase_id':purchase.id})
                db.commit();return result
            except Exception as exc:
                purchase.workflow={**s,'interrupted_node':name,'error_type':type(exc).__name__}
                trace.record(name,'ERROR',{'error_type':type(exc).__name__,'purchase_id':purchase.id})
                db.commit();raise
        graph.add_node(name,wrapped)
    graph.add_edge(START,'await_user_approval')
    graph.add_conditional_edges('await_user_approval',lambda s:'rejected' if s['status']=='REJECTED' else 'continue',{'rejected':END,'continue':'revalidate_offers'})
    graph.add_edge('revalidate_offers','execute_authorized_checkout');graph.add_edge('execute_authorized_checkout','verify_result')
    graph.add_conditional_edges('verify_result',lambda s:'unknown' if s['status']=='PAYMENT_UNKNOWN' else 'failure' if s['status'] in ['PARTIAL_FAILURE','PAYMENT_FAILED','COMPENSATION_PENDING'] else 'done',{'unknown':'await_reconciliation','failure':'report_checkout_or_payment_failure','done':END})
    graph.add_edge('await_reconciliation',END);graph.add_edge('report_checkout_or_payment_failure',END)
    graph.compile().invoke({'purchase_id':purchase_id,'request':request.model_dump(mode='json'),'completed':[]})
    return purchase
