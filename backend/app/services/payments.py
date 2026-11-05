from typing import Protocol, Literal
from dataclasses import dataclass

@dataclass(frozen=True)
class GatewayResult:
    status: Literal["PAID", "PAYMENT_FAILED"]

class PaymentGateway(Protocol):
    def charge(self, *, order_id: str, amount: int, simulate_failure: bool) -> GatewayResult: ...

class MockPaymentGateway:
    """Pure simulation; no credentials, network calls or real funds."""
    def charge(self, *, order_id: str, amount: int, simulate_failure: bool) -> GatewayResult:
        if amount <= 0:
            raise ValueError("Payment amount must be positive")
        return GatewayResult(status="PAYMENT_FAILED" if simulate_failure else "PAID")
