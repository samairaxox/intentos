"""Optional single-request smoke check; never invoked by application startup or tests unmocked."""
import argparse
from typing import Literal
from pydantic import BaseModel
from google import genai
from google.genai import types
from app.core.config import settings

class SmokeResult(BaseModel):
    ok:Literal[True]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-one-request',action='store_true')
    args=parser.parse_args(argv)
    if not args.allow_one_request:
        print('Not run: explicitly authorize one potentially billable request with --allow-one-request.');return 2
    if not settings.gemini_api_key:
        print('Not run: GEMINI_API_KEY is not configured.');return 2
    try:
        with genai.Client(api_key=settings.gemini_api_key,http_options=types.HttpOptions(timeout=30000)) as client:
            response=client.models.generate_content(model=settings.gemini_model,contents='Return JSON with ok true.',
                config=types.GenerateContentConfig(response_mime_type='application/json',response_schema=SmokeResult,
                    temperature=0,max_output_tokens=64,thinking_config=types.ThinkingConfig(thinking_budget=0)))
            SmokeResult.model_validate_json(response.text)
        print('Gemini smoke check passed: one structured request validated.');return 0
    except Exception as exc:
        print('Gemini smoke check failed; error_type='+type(exc).__name__);return 1

if __name__=='__main__':raise SystemExit(main())
