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


def test_explanations_render_only_catalog_facts():
    from app.services.gemini import Explanations
    recommendation={"product":{"id":"sample","price":65000,"ram_gb":16,"storage_gb":512,"weight_kg":1.4,"battery_hours":8,"processor_brand":"Intel","processor":"Core i5"},"score":82.5}
    service=GeminiService()
    with patch.object(service,"generate",return_value=Explanations(items=[{"product_id":"sample","reason_ids":["price","memory"]}])):
        assert service.explain([recommendation])=={"sample":"Demo price: INR 65,000. Memory: 16 GB RAM. All mandatory constraints passed."}
    with patch.object(service,"generate",return_value=Explanations(items=[{"product_id":"unknown","reason_ids":["price"]}])):
        with pytest.raises(AIUnavailable,match="invalid explanation references"):
            service.explain([recommendation])

def test_explanations_cannot_invent_fact_types():
    from pydantic import ValidationError
    from app.services.gemini import Explanations
    with pytest.raises(ValidationError):
        Explanations(items=[{"product_id":"sample","reason_ids":["invented_discount"]}])


def test_multi_intent_uses_official_structured_sdk(monkeypatch):
    from app.models.multi_schemas import MultiIntent, ItemRequirement
    monkeypatch.setattr(settings,'gemini_api_key','unit-test-placeholder')
    client=MagicMock()
    client.models.generate_content.return_value=SimpleNamespace(text=MultiIntent(total_budget=100000,items=[ItemRequirement(category='laptop'),ItemRequirement(category='monitor')]).model_dump_json())
    context=MagicMock();context.__enter__.return_value=client
    with patch('app.services.gemini.genai.Client',return_value=context):
        result=GeminiService().parse_multi('Laptop and monitor under 100000')
    assert len(result.items)==2
    assert client.models.generate_content.call_args.kwargs['config'].response_schema is MultiIntent
