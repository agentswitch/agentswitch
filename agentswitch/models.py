"""Unified model registry — maps friendly names to provider-specific IDs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelInfo:
    """A known model with per-provider name mappings."""

    id: str                                     # Unified name, e.g. "opus-4.6"
    name: str                                   # Display name, e.g. "Claude 4.6 Opus"
    family: str                                 # "claude", "gpt", "gemini", "grok"
    provider_ids: dict[str, str] = field(       # provider -> CLI model arg
        default_factory=dict,
    )
    capabilities: list[str] = field(            # e.g. ["thinking", "web_search"]
        default_factory=list,
    )

    @property
    def providers(self) -> list[str]:
        return list(self.provider_ids.keys())


# ── Registry ──────────────────────────────────────────────────────────────────
# Each entry maps a unified id to the CLI-specific --model value per provider.
# "web_search" means the *provider* exposes web search tools to that model.
# Claude Code has WebSearch built in; Cursor has it for most models; Codex does not.

MODELS: list[ModelInfo] = [
    # ── Claude ────────────────────────────────────────────────────────────
    ModelInfo(
        id="opus-4.6",
        name="Claude 4.6 Opus",
        family="claude",
        provider_ids={"claude": "claude-opus-4-6", "cursor": "opus-4.6"},
        capabilities=["web_search"],
    ),
    ModelInfo(
        id="opus-4.6-thinking",
        name="Claude 4.6 Opus (Thinking)",
        family="claude",
        provider_ids={"claude": "claude-opus-4-6", "cursor": "opus-4.6-thinking"},
        capabilities=["thinking", "web_search"],
    ),
    ModelInfo(
        id="sonnet-4.6",
        name="Claude 4.6 Sonnet",
        family="claude",
        provider_ids={"claude": "claude-sonnet-4-6", "cursor": "sonnet-4.6"},
        capabilities=["web_search"],
    ),
    ModelInfo(
        id="sonnet-4.6-thinking",
        name="Claude 4.6 Sonnet (Thinking)",
        family="claude",
        provider_ids={"claude": "claude-sonnet-4-6", "cursor": "sonnet-4.6-thinking"},
        capabilities=["thinking", "web_search"],
    ),
    ModelInfo(
        id="opus-4.5",
        name="Claude 4.5 Opus",
        family="claude",
        provider_ids={"claude": "claude-opus-4-5-20250520", "cursor": "opus-4.5"},
        capabilities=["web_search"],
    ),
    ModelInfo(
        id="opus-4.5-thinking",
        name="Claude 4.5 Opus (Thinking)",
        family="claude",
        provider_ids={"claude": "claude-opus-4-5-20250520", "cursor": "opus-4.5-thinking"},
        capabilities=["thinking", "web_search"],
    ),
    ModelInfo(
        id="sonnet-4.5",
        name="Claude 4.5 Sonnet",
        family="claude",
        provider_ids={"claude": "claude-sonnet-4-5-20241022", "cursor": "sonnet-4.5"},
        capabilities=["web_search"],
    ),
    ModelInfo(
        id="sonnet-4.5-thinking",
        name="Claude 4.5 Sonnet (Thinking)",
        family="claude",
        provider_ids={"claude": "claude-sonnet-4-5-20241022", "cursor": "sonnet-4.5-thinking"},
        capabilities=["thinking", "web_search"],
    ),
    ModelInfo(
        id="haiku-4.5",
        name="Claude 4.5 Haiku",
        family="claude",
        provider_ids={"claude": "claude-haiku-4-5-20251001"},
        capabilities=["web_search"],
    ),

    # ── GPT / OpenAI ─────────────────────────────────────────────────────
    ModelInfo(
        id="gpt-5.3-codex",
        name="GPT-5.3 Codex",
        family="gpt",
        provider_ids={"codex": "gpt-5.3-codex", "cursor": "gpt-5.3-codex"},
        capabilities=[],
    ),
    ModelInfo(
        id="gpt-5.3-codex-high",
        name="GPT-5.3 Codex High",
        family="gpt",
        provider_ids={"codex": "gpt-5.3-codex-high", "cursor": "gpt-5.3-codex-high"},
        capabilities=[],
    ),
    ModelInfo(
        id="gpt-5.2",
        name="GPT-5.2",
        family="gpt",
        provider_ids={"codex": "gpt-5.2", "cursor": "gpt-5.2"},
        capabilities=[],
    ),
    ModelInfo(
        id="gpt-5.2-codex",
        name="GPT-5.2 Codex",
        family="gpt",
        provider_ids={"codex": "gpt-5.2-codex", "cursor": "gpt-5.2-codex"},
        capabilities=[],
    ),
    ModelInfo(
        id="gpt-5.1-codex-mini",
        name="GPT-5.1 Codex Mini",
        family="gpt",
        provider_ids={"codex": "gpt-5.1-codex-mini", "cursor": "gpt-5.1-codex-mini"},
        capabilities=[],
    ),

    # ── Gemini ────────────────────────────────────────────────────────────
    ModelInfo(
        id="gemini-3.1-pro",
        name="Gemini 3.1 Pro",
        family="gemini",
        provider_ids={"gemini": "gemini-3.1-pro-preview", "cursor": "gemini-3.1-pro"},
        capabilities=["thinking", "web_search"],
    ),
    ModelInfo(
        id="gemini-3-pro",
        name="Gemini 3 Pro",
        family="gemini",
        provider_ids={"gemini": "gemini-3-pro-preview", "cursor": "gemini-3-pro"},
        capabilities=["thinking", "web_search"],
    ),
    ModelInfo(
        id="gemini-3-flash",
        name="Gemini 3 Flash",
        family="gemini",
        provider_ids={"gemini": "gemini-3-flash-preview", "cursor": "gemini-3-flash"},
        capabilities=["web_search"],
    ),
    ModelInfo(
        id="gemini-2.5-pro",
        name="Gemini 2.5 Pro",
        family="gemini",
        provider_ids={"gemini": "gemini-2.5-pro", "cursor": "gemini-2.5-pro"},
        capabilities=["thinking", "web_search"],
    ),
    ModelInfo(
        id="gemini-2.5-flash",
        name="Gemini 2.5 Flash",
        family="gemini",
        provider_ids={"gemini": "gemini-2.5-flash", "cursor": "gemini-2.5-flash"},
        capabilities=["web_search"],
    ),
    ModelInfo(
        id="gemini-2.5-flash-lite",
        name="Gemini 2.5 Flash Lite",
        family="gemini",
        provider_ids={"gemini": "gemini-2.5-flash-lite"},
        capabilities=[],
    ),

    # ── Grok ──────────────────────────────────────────────────────────────
    ModelInfo(
        id="grok",
        name="Grok",
        family="grok",
        provider_ids={"cursor": "grok"},
        capabilities=[],
    ),
]

# ── Lookup helpers ────────────────────────────────────────────────────────────

_BY_ID: dict[str, ModelInfo] = {m.id: m for m in MODELS}

# Reverse index: provider-specific ID → ModelInfo
_BY_PROVIDER_ID: dict[str, ModelInfo] = {}
for _m in MODELS:
    for _pid in _m.provider_ids.values():
        _BY_PROVIDER_ID.setdefault(_pid, _m)


def get_model(unified_id: str) -> ModelInfo | None:
    """Look up a model by unified ID."""
    return _BY_ID.get(unified_id)


def resolve_model(name: str, provider: str) -> str:
    """Resolve a user-supplied model name to the provider-specific CLI arg.

    Tries in order:
      1. Exact unified ID match → provider-specific ID
      2. Already a valid provider-specific ID → pass through
      3. Unknown → return as-is (let the CLI handle it)
    """
    model = _BY_ID.get(name)
    if model and provider in model.provider_ids:
        return model.provider_ids[provider]
    return name


def identify_model(provider_id: str) -> ModelInfo | None:
    """Given a provider-specific model ID, find the unified ModelInfo."""
    return _BY_PROVIDER_ID.get(provider_id)


def models_for_provider(provider: str) -> list[ModelInfo]:
    """Return all known models available on a given provider."""
    return [m for m in MODELS if provider in m.provider_ids]


def all_families() -> list[str]:
    """Return sorted list of model families."""
    return sorted({m.family for m in MODELS})
