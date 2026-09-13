"""Model provider cards for the setup console and CLI: presets, import modules, default key names."""

from __future__ import annotations

import importlib.util

from paid_media_agent.config import Settings
from paid_media_agent.domain.common import JsonValue

MODEL_PRESETS: tuple[dict[str, JsonValue], ...] = (
    {
        "id": "langsmith",
        "label": "LangSmith Gateway",
        "model": "langsmith:anthropic/claude-sonnet-4-6",
        "key": "LANGSMITH_API_KEY",
        "url": "https://smith.langchain.com/settings",
        "note": "One key, every provider, traced",
        "package": "",
        "recommended": True,
        "logo": "langchain",
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "logo": "anthropic",
        "model": "anthropic:claude-sonnet-4-6",
        "key": "ANTHROPIC_API_KEY",
        "package": "",
        "extra": "",
        "url": "https://console.anthropic.com/settings/keys",
        "note": "Native tool search",
        "recommended": False,
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "logo": "openai",
        "model": "openai:gpt-5.5",
        "key": "OPENAI_API_KEY",
        "package": "",
        "extra": "",
        "url": "https://platform.openai.com/api-keys",
        "note": "Native tool search",
    },
    {
        "id": "google",
        "label": "Google",
        "logo": "gemini",
        "model": "google_genai:gemini-3-flash",
        "key": "GOOGLE_API_KEY",
        "package": "langchain_google_genai",
        "extra": "google",
        "url": "https://aistudio.google.com/app/apikey",
        "note": "Portable selector",
    },
    {
        "id": "groq",
        "label": "Groq",
        "logo": "groq",
        "model": "groq:llama-3.3-70b-versatile",
        "key": "GROQ_API_KEY",
        "package": "langchain_groq",
        "extra": "groq",
        "url": "https://console.groq.com/keys",
        "note": "Fast open models",
    },
    {
        "id": "xai",
        "label": "xAI",
        "logo": "xai",
        "model": "xai:grok-4",
        "key": "XAI_API_KEY",
        "package": "langchain_xai",
        "extra": "xai",
        "url": "https://console.x.ai/",
        "note": "Grok",
    },
    {
        "id": "mistral",
        "label": "Mistral",
        "logo": "mistral",
        "model": "mistralai:mistral-large-latest",
        "key": "MISTRAL_API_KEY",
        "package": "langchain_mistralai",
        "extra": "mistral",
        "url": "https://console.mistral.ai/api-keys",
        "note": "Open weights",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "logo": "deepseek",
        "model": "deepseek:deepseek-chat",
        "key": "DEEPSEEK_API_KEY",
        "package": "langchain_deepseek",
        "extra": "deepseek",
        "url": "https://platform.deepseek.com/api_keys",
        "note": "Open weights",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "logo": "openrouter",
        "model": "openai:moonshotai/kimi-k2",
        "key": "OPENROUTER_API_KEY",
        "package": "langchain_openai",
        "extra": "",
        "base_url": "https://openrouter.ai/api/v1",
        "url": "https://openrouter.ai/keys",
        "note": "Kimi, GLM, and more",
    },
    {
        "id": "moonshot",
        "label": "Kimi",
        "logo": "moonshot",
        "model": "openai:kimi-k2-0905-preview",
        "key": "MOONSHOT_API_KEY",
        "package": "langchain_openai",
        "extra": "",
        "base_url": "https://api.moonshot.ai/v1",
        "url": "https://platform.moonshot.ai/",
        "note": "OpenAI-compatible",
    },
    {
        "id": "zhipu",
        "label": "GLM",
        "logo": "zhipu",
        "model": "openai:glm-4.6",
        "key": "ZHIPU_API_KEY",
        "package": "langchain_openai",
        "extra": "",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "url": "https://open.bigmodel.cn/",
        "note": "OpenAI-compatible",
    },
    {
        "id": "custom",
        "label": "Custom",
        "logo": "custom",
        "model": "",
        "key": "",
        "package": "",
        "extra": "",
        "url": "",
        "note": "Your provider, key, and base URL",
    },
)
"""Model provider cards for the wizard. Key names are allowlisted env names; nothing else is written.

OpenAI-compatible presets use the `openai:` prefix with a base URL and their own key env var,
which `PAID_MEDIA_MODEL_API_KEY_ENV` hands to the client. Examples are configuration defaults; the model picker reads the provider API.
Runtime tool-selection capabilities remain separate from model availability.
"""


def model_preset_payloads() -> list[dict[str, JsonValue]]:
    """Provider setup metadata. Available models come from each provider's live API."""
    return [dict(preset) for preset in MODEL_PRESETS]


PROVIDER_IMPORT_MODULES: dict[str, str] = {
    "anthropic": "langchain_anthropic",
    "openai": "langchain_openai",
    "google_genai": "langchain_google_genai",
    "groq": "langchain_groq",
    "xai": "langchain_xai",
    "mistralai": "langchain_mistralai",
    "deepseek": "langchain_deepseek",
    "langsmith": "langchain_openai",
    "scripted": "paid_media_agent",
}


PROVIDER_DEFAULT_KEYS: dict[str, str] = {
    "langsmith": "LANGSMITH_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "xai": "XAI_API_KEY",
    "mistralai": "MISTRAL_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


def model_key_env(settings: Settings) -> str | None:
    """The env var that must hold the key for the configured model."""
    if settings.paid_media_model_api_key_env:
        return settings.paid_media_model_api_key_env
    return PROVIDER_DEFAULT_KEYS.get(settings.model_settings().provider)


def _module_available(provider: str) -> bool:
    module = PROVIDER_IMPORT_MODULES.get(provider)
    return module is not None and importlib.util.find_spec(module) is not None
