"""Azure OpenAI as a second model provider, authenticated with Microsoft Entra ID (no API key).

Locally the token comes from `az login` through DefaultAzureCredential; in Azure the same code picks up a managed
identity. The caller needs the "Cognitive Services OpenAI User" role on the Azure OpenAI resource.

Configured by environment variables (see .env.example):
  AZURE_OPENAI_ENDPOINT    e.g. https://<resource>.openai.azure.com/
  AZURE_OPENAI_DEPLOYMENT  the deployment name, e.g. gpt-41-mini
"""
from __future__ import annotations

import json
import os

API_VERSION = "2024-10-21"


def configured() -> bool:
    return bool(os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_DEPLOYMENT"))


def _client():
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider  # lazy: optional dependency
    from openai import AzureOpenAI

    token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
    return AzureOpenAI(azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"], azure_ad_token_provider=token_provider,
                       api_version=API_VERSION)


def json_completion(system: str, user: str, schema: dict, name: str = "result", client=None) -> dict:
    """One chat completion whose output is forced to match `schema` (structured outputs)."""
    client = client or _client()
    response = client.chat.completions.create(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
    )
    return json.loads(response.choices[0].message.content or "{}")
