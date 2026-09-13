"""Read model catalogs from fixed official endpoints, using only that provider's key."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from paid_media_agent.admin.envfile import apply_env_file
from paid_media_agent.admin.model_presets import MODEL_PRESETS
from paid_media_agent.domain.common import JsonValue

# Never accept a URL from the browser or follow a provider redirect with credentials.
CATALOG_URLS = {
    "langsmith": "https://gateway.smith.langchain.com/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models",
    "openai": "https://api.openai.com/v1/models",
    "google": "https://generativelanguage.googleapis.com/v1beta/models",
    "groq": "https://api.groq.com/openai/v1/models",
    "xai": "https://api.x.ai/v1/language-models",
    "mistral": "https://api.mistral.ai/v1/models",
    "deepseek": "https://api.deepseek.com/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "moonshot": "https://api.moonshot.ai/v1/models",
}
MAX_PAGES = 10


class ModelCatalogError(ValueError):
    """A safe message for the console, without upstream bodies or credentials."""


def _is_chat_model(provider: str, item: dict[str, Any], model_id: str) -> bool:
    if item.get("active") is False:
        return False
    if provider == "google":
        methods = item.get("supportedGenerationMethods")
        return isinstance(methods, list) and "generateContent" in methods
    capabilities = item.get("capabilities")
    if isinstance(capabilities, dict) and capabilities.get("completion_chat") is False:
        return False
    architecture = item.get("architecture")
    if isinstance(architecture, dict):
        outputs = architecture.get("output_modalities")
        if outputs is not None and (not isinstance(outputs, list) or "text" not in outputs):
            return False
    # OpenAI-style catalogs also include embeddings, speech, and image-only models.
    return not re.search(
        r"embedding|moderation|whisper|tts|transcribe|realtime|dall-e|gpt-image|sora|guard|\baudio\b",
        model_id,
        re.IGNORECASE,
    )


def list_models(root: Path, provider: str, *, api_key: str = "") -> dict[str, JsonValue]:
    preset = next((p for p in MODEL_PRESETS if p["id"] == provider), None)
    if preset is None:
        raise ModelCatalogError("Unknown model provider.")
    url = CATALOG_URLS.get(provider)
    if not url:
        raise ModelCatalogError("This provider has no supported model-list API. Enter a model ID.")
    key_name = str(preset["key"])
    apply_env_file(root)
    key = api_key.strip() or os.environ.get(key_name, "")
    if not key and provider != "openrouter":
        raise ModelCatalogError(f"Add your {preset['label']} API key to load available models.")
    if any(character in key for character in ("\r", "\n", "\x00")):
        raise ModelCatalogError("The API key must be a single line.")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    params: dict[str, str | int] = {}
    if provider == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        params["limit"] = 1000
    elif provider == "google":
        headers = {"x-goog-api-key": key}
        params["pageSize"] = 1000

    rows: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            for _ in range(MAX_PAGES):
                response = client.get(url, headers=headers, params=params)
                if response.status_code in (401, 403):
                    raise ModelCatalogError("Check your API key and its model-list permissions.")
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ModelCatalogError("The provider returned an invalid model catalog.")
                page = payload.get("models" if provider in ("google", "xai") else "data")
                if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
                    raise ModelCatalogError("The provider returned an invalid model catalog.")
                rows.extend(page)
                cursor = (
                    payload.get("nextPageToken")
                    if provider == "google"
                    else payload.get("last_id")
                    if payload.get("has_more")
                    else None
                )
                if not cursor:
                    break
                if not isinstance(cursor, str):
                    raise ModelCatalogError("The provider returned an invalid catalog cursor.")
                params["pageToken" if provider == "google" else "after_id"] = cursor
            else:
                raise ModelCatalogError(
                    "The provider's catalog is too large to load. Enter a model ID."
                )
    except httpx.HTTPStatusError as exc:
        raise ModelCatalogError(
            f"Could not load models (provider returned HTTP {exc.response.status_code}). Try again."
        ) from None
    except httpx.RequestError:
        raise ModelCatalogError("Could not reach the model provider. Try again.") from None
    except ValueError as exc:
        if isinstance(exc, ModelCatalogError):
            raise
        raise ModelCatalogError("The provider returned an invalid model catalog.") from None

    prefix = str(preset["model"]).split(":", 1)[0]
    models: dict[str, dict[str, JsonValue]] = {}
    for item in rows:
        model_id = item.get("name") if provider == "google" else item.get("id")
        if not isinstance(model_id, str) or not model_id or len(model_id) > 250:
            continue
        model_id = model_id.removeprefix("models/")
        if not _is_chat_model(provider, item, model_id):
            continue
        spec = f"{prefix}:{model_id}"
        name = item.get("display_name") or item.get("displayName") or item.get("name")
        models[spec] = {
            "id": spec,
            "name": name if isinstance(name, str) else model_id,
            "provider": model_id.split("/", 1)[0].lstrip("~")
            if provider in ("langsmith", "openrouter")
            else provider,
        }
    return {
        "models": list(models.values()),
        "source": url,
        "fetched_at": datetime.now(UTC).isoformat(),
    }
