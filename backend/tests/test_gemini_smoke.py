from unittest.mock import MagicMock,patch
from types import SimpleNamespace
from app.services.gemini_smoke import main
from app.core.config import settings


def test_smoke_needs_explicit_opt_in():
    with patch('app.services.gemini_smoke.genai.Client') as constructor:
        assert main([])==2
        constructor.assert_not_called()


def test_smoke_is_one_bounded_mocked_request(monkeypatch):
    monkeypatch.setattr(settings,'gemini_api_key','unit-test-placeholder')
    client=MagicMock();client.models.generate_content.return_value=SimpleNamespace(text='{"ok":true}')
    context=MagicMock();context.__enter__.return_value=client
    with patch('app.services.gemini_smoke.genai.Client',return_value=context):assert main(['--allow-one-request'])==0
    client.models.generate_content.assert_called_once()
    assert client.models.generate_content.call_args.kwargs['config'].max_output_tokens==64
