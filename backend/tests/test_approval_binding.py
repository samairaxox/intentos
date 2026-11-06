from decimal import Decimal
import pytest
from sqlalchemy import select
from test_api import client,make_order
from test_commerce_payments import db,purchase,approve
from app.models.entities import Product,Order
from app.models.commerce import MerchantSuborder
from app.services.approval import canonical_lines,fingerprint
from app.commerce.payments import PaymentAuthorizationService
from fastapi import HTTPException


def test_canonical_money_and_line_order():
    a=canonical_lines([{'product_id':'b'},{'product_id':'a'}],1,'INR',Decimal('100'))
    b=canonical_lines([{'product_id':'a'},{'product_id':'b'}],1,'INR','100.00')
    assert fingerprint(a)==fingerprint(b)
    assert fingerprint(a)!=fingerprint({**a,'plan_version':2})


@pytest.mark.parametrize('change',[{'seller':'changed'},{'ram_gb':32},{'currency':'USD'},{'shipping':1},{'available':False}])
def test_legacy_material_terms_invalidate_approval(client,change):
    order,_=make_order(client,'binding-order-001');path='/api/v1/orders/'+order['id']
    assert client.post(path+'/approve',json={'approved':True}).status_code==200
    with client.factory() as session:
        stored=session.get(Order,order['id']);assert len(stored.authorization_digest)==64
        product=session.get(Product,order['product_id']);product.data={**product.data,**change};session.commit()
    assert client.post(path+'/pay',json={'idempotency_key':'binding-payment-001'}).status_code==409
    assert client.get(path).json()['status']=='CANCELLED'


def test_suborder_collection_is_bound(db,purchase):
    approve(db,purchase)
    sub=db.scalars(select(MerchantSuborder)).first()
    sub.items=[{**line,'quantity':line['quantity']+1} for line in sub.items];db.commit()
    with pytest.raises(HTTPException):PaymentAuthorizationService().verify(db,purchase)
    assert purchase.status=='APPROVAL_INVALIDATED'
