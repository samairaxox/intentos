from abc import ABC,abstractmethod
from decimal import Decimal
from sqlalchemy.orm import sessionmaker
from app.models.commerce import MockProviderReceipt

class PaymentProvider(ABC):
    provider_id:str
    @abstractmethod
    def execute(self,*,amount:Decimal,idempotency_key:str,simulation:str)->str: ...
    @abstractmethod
    def lookup(self,idempotency_key:str)->str: ...
    @abstractmethod
    def compensate(self,idempotency_key:str,pending:bool=False)->str: ...

class MockPaymentProvider(PaymentProvider):
    """Independent durable mock ledger, not a claim about a real payment network."""
    provider_id='mock'
    def __init__(self,bind):self.factory=sessionmaker(bind,expire_on_commit=False)

    def execute(self,*,amount,idempotency_key,simulation):
        with self.factory() as ledger:
            receipt=ledger.get(MockProviderReceipt,idempotency_key)
            if receipt:
                if receipt.amount!=amount:raise ValueError('Provider idempotency amount mismatch')
                return receipt.outcome
            outcome='FAILED' if simulation=='failure' else 'UNKNOWN' if simulation=='timeout_unknown' else 'CAPTURED'
            ledger.add(MockProviderReceipt(idempotency_key=idempotency_key,amount=amount,outcome=outcome))
            ledger.commit()
        if simulation in ['timeout_captured','timeout_unknown']:raise TimeoutError('Mock provider response timed out; outcome must be reconciled')
        return outcome

    def lookup(self,idempotency_key):
        with self.factory() as ledger:
            receipt=ledger.get(MockProviderReceipt,idempotency_key)
            return receipt.outcome if receipt else 'UNKNOWN'

    def compensate(self,idempotency_key,pending=False):
        with self.factory() as ledger:
            receipt=ledger.get(MockProviderReceipt,idempotency_key)
            if not receipt or receipt.outcome not in ['CAPTURED','REFUND_PENDING','REFUNDED']:
                return 'UNKNOWN'
            if receipt.outcome=='REFUNDED':return 'REFUNDED'
            receipt.outcome='REFUND_PENDING' if pending else 'REFUNDED'
            ledger.commit()
            return receipt.outcome
