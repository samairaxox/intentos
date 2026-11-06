"""Explicit operator-only adoption of unowned historical sessions. Never exposed over HTTP."""
import argparse
from sqlalchemy import update
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import PurchaseSession

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner',required=True);parser.add_argument('--confirm',action='store_true')
    args=parser.parse_args()
    if not args.confirm or args.owner not in settings.auth_tokens.values():parser.error('Explicit confirmation and an operator-configured identity are required')
    with SessionLocal() as db:
        changed=db.execute(update(PurchaseSession).where(PurchaseSession.owner_id.is_(None)).values(owner_id=args.owner))
        db.commit();print(f'Assigned {changed.rowcount} unowned historical sessions; existing ownership was not changed.')
