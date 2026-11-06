from app.models.commerce import WorkflowTrace

SAFE_KEYS={"duration_ms","input_tokens","output_tokens","total_tokens","provider_id","product_count","offer_count","error_type","attempt","suborder_id","purchase_id","reason","state","revised_plan_id"}

class TraceRecorder:
    def __init__(self,db,workflow_id,session_id):
        self.db=db;self.workflow_id=workflow_id;self.session_id=session_id

    def record(self,node,status,details=None):
        safe={k:v for k,v in (details or {}).items() if k in SAFE_KEYS and isinstance(v,(str,int,float,bool,type(None)))}
        # No prompts, response bodies, credentials or payment instruments enter trace details.
        self.db.add(WorkflowTrace(workflow_id=self.workflow_id,session_id=self.session_id,node=node,status=status,details=safe))
