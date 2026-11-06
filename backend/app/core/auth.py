"""Local MVP bearer credentials, provisioned by the operator; no passwords or anonymous identities."""
from contextvars import ContextVar
from hmac import compare_digest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import event,inspect
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.entities import Base,PurchaseSession

current_owner=ContextVar('purchase_owner',default=None)


async def authentication(request,call_next):
    if not request.url.path.startswith('/api/') or request.method=='OPTIONS':return await call_next(request)
    if not settings.auth_tokens:
        return JSONResponse(status_code=503,content={'detail':'Operator-provisioned authentication is not configured'})
    scheme,_,credential=request.headers.get('authorization','').partition(' ')
    owner=None
    if scheme.lower()=='bearer' and credential:
        for token,identity in settings.auth_tokens.items():
            if compare_digest(credential.encode(),token.encode()):owner=identity
    if not owner:return JSONResponse(status_code=401,headers={'WWW-Authenticate':'Bearer'},content={'detail':'A valid bearer credential is required'})
    privileged='/demo/' in request.url.path or request.url.path.endswith('/simulate-change') or request.url.path.endswith('/offers/refresh')
    if privileged and owner not in settings.auth_admins:return JSONResponse(status_code=403,content={'detail':'Operator privileges required for global demo mutations'})
    context=current_owner.set(owner)
    try:return await call_next(request)
    finally:current_owner.reset(context)


@event.listens_for(Session,'before_flush')
def assign_ownership(session,flush_context,instances):
    owner=current_owner.get()
    if owner is None:return  # trusted internal jobs/tests, not HTTP requests
    for row in session.new:
        if isinstance(row,PurchaseSession):row.owner_id=owner
    for row in session.dirty:
        if isinstance(row,PurchaseSession) and inspect(row).attrs.owner_id.history.has_changes():
            raise HTTPException(403,'Purchase ownership cannot be reassigned through the API')


@event.listens_for(Session,'loaded_as_persistent')
def enforce_ownership(session,row):
    owner=current_owner.get()
    if owner is None:return
    if isinstance(row,PurchaseSession):
        if row.owner_id!=owner:raise HTTPException(404,'Purchase resource not found')
        return
    if hasattr(row,'session_id'):
        root=session.get(PurchaseSession,row.session_id)
        if not root or root.owner_id!=owner:raise HTTPException(404,'Purchase resource not found')
        return
    # Follow declared parent foreign keys so carts, payments, attempts, links and
    # transactions inherit the root session's owner, including direct child-ID routes.
    tables={mapper.local_table.name:mapper.class_ for mapper in Base.registry.mappers}
    for column in row.__table__.columns:
        for foreign in column.foreign_keys:
            parent=tables.get(foreign.column.table.name)
            value=getattr(row,column.key)
            if parent is not None and value is not None:session.get(parent,value)
