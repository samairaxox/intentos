from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from app.services.gemini import GeminiService, AIUnavailable
from app.core.config import settings
from app.models.schemas import Intent

def test_official_sdk_structured_output(monkeypatch):
    monkeypatch.setattr(settings,"gemini_api_key","unit-test-placeholder")
    client=MagicMock()
    client.models.generate_content.return_value=SimpleNamespace(text=Intent(category="laptop",max_budget=75000).model_dump_json())
    context=MagicMock()
    context.__enter__.return_value=client
    with patch("app.services.gemini.genai.Client",return_value=context):
        result=GeminiService().parse("Laptop under 75000")
    assert result.max_budget==75000
    kwargs=client.models.generate_content.call_args.kwargs
    assert kwargs["config"].response_schema is Intent
    assert kwargs["config"].response_mime_type=="application/json"

def test_missing_key_is_transparent(monkeypatch):
    monkeypatch.setattr(settings,"gemini_api_key","")
    with pytest.raises(AIUnavailable,match="not configured"):
        GeminiService().parse("Laptop under 75000")

def test_sdk_failure_is_transparent(monkeypatch):
    monkeypatch.setattr(settings,"gemini_api_key","unit-test-placeholder")
    with patch("app.services.gemini.genai.Client",side_effect=RuntimeError("offline")):
        with pytest.raises(AIUnavailable,match="Gemini request failed"):
            GeminiService().parse("Laptop under 75000")
