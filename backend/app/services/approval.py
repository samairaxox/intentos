"""Canonical server-side purchase terms shared by all checkout generations."""
import hashlib
import json
from decimal import Decimal
from sqlalchemy import select
from fastapi import HTTPException
from app.models.entities import Product,Cart,PurchasePlan


def money(value):
    number=Decimal(str(value))
    if not number.is_finite() or number<0 or number!=number.quantize(Decimal('.01')):
        raise HTTPException(409,'Invalid authoritative monetary terms')
    return format(number,'.2f')


def fingerprint(terms):
    return hashlib.sha256(json.dumps(terms,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def canonical_lines(lines,version,currency,total):
    return {'schema':'purchase-terms-v1','plan_version':version,'currency':currency,'total':money(total),
        'lines':sorted(lines,key=lambda line:json.dumps(line,sort_keys=True,separators=(',',':')))}


def legacy_terms(db,order):
    version=1
    if order.cart_id:
        cart=db.get(Cart,order.cart_id);plan=db.get(PurchasePlan,cart.plan_id)
        version={'plan':plan.revision,'cart':cart.version}
        selected=[(line['product']['id'],line['quantity']) for line in cart.snapshot['items']]
    else:selected=[(order.product_id,1)]
    lines=[]
    for product_id,quantity in sorted(selected):
        product=db.scalar(select(Product).where(Product.id==product_id).with_for_update().execution_options(populate_existing=True))
        if not product:raise HTTPException(409,'Approved product no longer exists')
        p=product.data
        lines.append({'product_id':product_id,'merchant_id':p.get('merchant_id',p['seller']),
            'offer_id':p.get('offer_id','catalog:'+product_id),'quantity':quantity,'currency':p['currency'],
            'unit_final':money(p['price']),'shipping':money(p.get('shipping',0)),'fees':money(p.get('fees',0)),
            'identity':{k:p.get(k) for k in ['name','brand','model','category','specifications','processor_brand','processor','ram_gb','storage_gb','weight_kg','battery_hours','gpu','os']}})
    return canonical_lines(lines,version,order.currency or lines[0]["currency"],order.amount)


def commerce_terms(db,purchase,plan,suborders):
    lines=[]
    for sub in suborders:
        for line in sub.items:
            offer=line['offer']
            lines.append({'suborder_id':sub.id,'suborder_merchant_id':sub.merchant_id,'suborder_amount':money(sub.amount),
                'product_id':line['product']['id'],'merchant_id':offer['merchant_id'],'offer_id':offer['id'],
                'quantity':line['quantity'],'currency':offer['currency'],'pricing':{k:money(line['pricing'][k]) for k in ['base_price','shipping','fees','estimated_taxes','confirmed_discount','final_price']},
                'line_total':money(line['line_total']),'product':line['product']})
    terms=canonical_lines(lines,{'plan_id':plan.id,'version':plan.version},plan.intent.get('currency','INR'),purchase.amount)
    terms['snapshot']={**purchase.snapshot,'items':sorted(purchase.snapshot.get('items',[]),key=lambda line:json.dumps(line,sort_keys=True))}
    return terms
