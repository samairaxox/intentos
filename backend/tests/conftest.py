import pytest
from app.core.config import settings

@pytest.fixture(autouse=True)
def local_test_credentials(monkeypatch):
    monkeypatch.setattr(settings,'auth_tokens',{'test-owner-token-00000000000000000001':'user-a','test-owner-token-00000000000000000002':'user-b'})
    monkeypatch.setattr(settings,'auth_admins',['user-a'])
