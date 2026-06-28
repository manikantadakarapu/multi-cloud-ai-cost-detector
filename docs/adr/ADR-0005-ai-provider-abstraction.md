# ADR-0005: AI Provider Abstraction

> **Status:** Accepted
>
> **Date:** 2026-06-28 (Sprint 0.2)
>
> **Deciders:** Platform team
>
> **Technical Story:** [MCAICD-6](https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/issues/6) — AI analysis engine (planned Sprint 0.5)

---

## Context

MCAICD's core value proposition is **AI-powered cost recommendations**. The
platform will ingest normalised cost data from AWS, Azure, and GCP, detect
anomalies, and then call an AI model to generate ranked, actionable
recommendations with estimated savings and human-readable rationales.

The AI model landscape is fragmented and fast-moving:

- **OpenAI** (GPT-4o, GPT-4o-mini, o1 series)
- **Google** (Gemini 1.5 Pro/Flash, 2.0)
- **Anthropic** (Claude 3.5 Sonnet/Haiku/Opus)
- **Azure OpenAI** (enterprise-hosted OpenAI models with data residency)
- **Open-source** (Llama 3.1, Nemotron, Qwen) via self-hosted or managed
  endpoints (Together, Fireworks, Groq)

Each provider has a different API shape, authentication model, rate limits,
pricing, latency profile, and capability ceiling. Committing to a single
provider at the platform level would create **vendor lock-in** — the very
problem MCAICD solves for cloud costs.

The abstraction must be decided *before* the AI engine is implemented
(Sprint 0.5) so that the domain service that orchestrates recommendations
depends on a stable interface, not a concrete SDK.

---

## Decision

**Introduce an `AIProvider` protocol (abstract interface) that encapsulates
all AI model interactions. The domain layer depends only on the protocol.
Concrete implementations live in `app/providers/ai/` and are selected at
startup via configuration.**

### The Protocol

```python
# app/providers/ai/base.py (planned)
from typing import Protocol
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse

class AIProvider(Protocol):
    """Contract for AI-powered cost recommendation generation."""

    async def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        """
        Generate cost optimisation recommendations.

        Args:
            request: Normalised cost data, anomaly context, and constraints.

        Returns:
            Ranked recommendations with estimated savings, confidence, and rationale.

        Raises:
            ProviderError: On API failure, rate limit, or invalid response.
            ProviderUnavailableError: On transient failure (retryable).
        """
        ...
```

### Configuration

```python
# app/core/config.py (extension planned)
class Settings(BaseSettings):
    ...
    ai_provider: Literal["openai", "gemini", "claude", "azure_openai"] = "openai"
    ai_model: str = "gpt-4o-mini"
    ai_api_key: str | None = None          # Injected via secret manager in prod
    ai_base_url: str | None = None         # For Azure OpenAI / self-hosted endpoints
    ai_timeout_seconds: int = 30
    ai_max_retries: int = 2
    ai_fallback_provider: Literal["openai", "gemini", "claude", "azure_openai", "none"] = "gemini"
```

### Provider Factory

```python
# app/providers/ai/factory.py (planned)
from app.core.config import settings
from app.providers.ai.base import AIProvider
from app.providers.ai.openai import OpenAIProvider
from app.providers.ai.gemini import GeminiProvider
from app.providers.ai.claude import ClaudeProvider
from app.providers.ai.azure_openai import AzureOpenAIProvider

_PROVIDER_MAP: dict[str, type[AIProvider]] = {
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "claude": ClaudeProvider,
    "azure_openai": AzureOpenAIProvider,
}

def get_ai_provider() -> AIProvider:
    provider_cls = _PROVIDER_MAP[settings.ai_provider]
    return provider_cls(
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        base_url=settings.ai_base_url,
        timeout=settings.ai_timeout_seconds,
        max_retries=settings.ai_max_retries,
    )
```

### Domain Service Usage

```python
# app/services/recommendation.py (planned)
from app.providers.ai.base import AIProvider
from app.providers.ai.factory import get_ai_provider

class RecommendationService:
    def __init__(self, provider: AIProvider | None = None) -> None:
        self._provider = provider or get_ai_provider()

    async def generate(self, cost_data: CostCorpus) -> list[Recommendation]:
        request = RecommendationRequest.from_cost_corpus(cost_data)
        response = await self._provider.recommend(request)
        return response.recommendations
```

---

## Alternatives Considered

### Direct SDK Calls in the Service Layer

| Criterion | Assessment |
| --------- | ---------- |
| **Simplicity** | Fewer files. `import openai` and call `client.chat.completions.create()` directly. |
| **Lock-in** | The service is now coupled to OpenAI's request/response shape, error types, and retry semantics. Switching providers requires rewriting the service. |
| **Testing** | Requires mocking the OpenAI SDK. The mock must mirror the SDK's evolving API. |
| **Fallback** | Implementing a fallback provider means a giant `if provider == "openai": ... elif provider == "gemini": ...` block in the service. |
| **Observability** | Metrics and logging are provider-specific. No unified contract. |

**Verdict:** Rejected. The lock-in cost exceeds the boilerplate cost of the
abstraction.

### Single Provider with a Wrapper Function

| Criterion | Assessment |
| --------- | ---------- |
| **Simplicity** | One function `call_llm(prompt) -> str`. |
| **Flexibility** | The prompt template is the only customisation point. Cannot express provider-specific features (structured output, tool use, system prompts, thinking budgets). |
| **Type safety** | Returns `str`. The service must parse JSON from the string. Fragile. |
| **Evolution** | As providers add features (structured output, citations, reasoning traces), the wrapper must grow ad-hoc parameters. |

**Verdict:** Rejected. The protocol approach preserves type safety and
extensibility.

### Multi-Provider Gateway (LiteLLM, Portkey, Helicone)

| Criterion | Assessment |
| --------- | ---------- |
| **Abstraction level** | These gateways unify the *HTTP* layer. The application still sends a provider-agnostic request and gets a provider-agnostic response. |
| **Dependency** | Adds a network hop (gateway) or a heavy Python dependency (LiteLLM). |
| **Control** | The gateway controls the prompt format, retry logic, and error mapping. Custom behaviour requires gateway configuration, not code. |
| **Cost** | Gateway hosting (self-hosted or SaaS) adds operational complexity. |
| **Fit** | Excellent for *routing* and *observability* across providers. Not a replacement for a domain-level protocol that defines *what* a recommendation request looks like. |

**Verdict:** Complementary, not a replacement. A gateway can sit *behind* a
provider implementation (e.g., `OpenAIProvider` routes via LiteLLM) but
the domain still needs its own protocol to define the recommendation
contract.

### Protocol with Pydantic Models (Chosen)

| Criterion | Assessment |
| --------- | ---------- |
| **Type safety** | `RecommendationRequest` and `RecommendationResponse` are Pydantic models. The protocol is `async def recommend(request) -> Response`. Full static checking. |
| **Extensibility** | New fields in the request/response are schema changes, not protocol breaks. Providers can ignore unknown fields (`extra="allow"` on request, `extra="ignore"` on response). |
| **Testing** | A `FakeAIProvider` implements the protocol with canned responses. Zero network, zero SDK, deterministic. |
| **Observability** | The protocol defines the boundary. Metrics (latency, tokens, cost) are emitted at the protocol boundary, not inside each provider. |
| **Fallback** | The service can catch `ProviderUnavailableError` and retry with `get_fallback_provider()`. |
| **Boilerplate** | One protocol + one factory + N implementations. ~50 lines of infrastructure for a lifetime of vendor freedom. |

**Verdict:** Accepted. The protocol + Pydantic approach is the minimum
abstraction that preserves type safety, testability, and vendor
independence.

---

## Consequences

### Positive

- **Zero vendor lock-in.** Switching from OpenAI to Gemini is a
  configuration change (`ai_provider: "gemini"`) plus ensuring the
  `GeminiProvider` implementation exists. The recommendation service does
  not change.
- **Enterprise readiness.** Azure OpenAI is a first-class provider. Enterprise
  customers with data residency requirements get a supported path without
  forking the platform.
- **Fallback resilience.** If the primary provider hits a rate limit or
  outage, the service can transparently retry with the configured fallback
  provider. The user sees a slightly higher latency, not an error.
- **Testability.** Unit tests for `RecommendationService` inject a
  `FakeAIProvider`. No API keys, no network, no flakiness.
- **Cost control.** Different providers/models have different price/performance
  profiles. The configuration lets operators optimise for their budget
  without code changes.
- **Observability.** Metrics are emitted at the protocol boundary:
  `ai_request_duration_seconds`, `ai_tokens_consumed`, `ai_estimated_cost_usd`,
  `ai_provider_errors_total`. The labels include `provider` and `model`.

### Negative

- **Abstraction leakage risk.** If a provider has a unique capability
  (e.g., OpenAI's `response_format: json_schema`, Claude's `thinking`
  budget), the protocol must either expose it generically or the provider
  implementation must degrade gracefully. The protocol will evolve, but
  changes are schema additions, not breaks.
- **Implementation burden.** Each provider needs a concrete class. The
  first provider (OpenAI) sets the bar; subsequent providers must match
  the contract. This is a one-time cost per provider.
- **Prompt engineering divergence.** The prompt template that produces
  high-quality recommendations may need provider-specific tuning. The
  protocol allows `provider_specific_hints: dict[str, Any]` in the
  request, but this is a controlled escape hatch.

### Neutral

- **No AI yet.** This ADR is written *before* the AI engine exists. The
  protocol is a design-time contract. The first implementation (Sprint 0.5)
  will validate it.

---

## Future Considerations

- **Structured output enforcement:** All providers will be required to
  return valid JSON matching `RecommendationResponse`. The protocol can
  mandate `response_format: json_schema` (OpenAI) or equivalent for other
  providers. Providers that don't support structured output will use a
  retry-with-repair loop.
- **Streaming responses:** For long recommendation sets, streaming the
  response token-by-token improves perceived latency. The protocol can add
  an async generator variant: `async def recommend_stream(...) ->
  AsyncIterator[RecommendationChunk]`.
- **Fine-tuned models:** If the platform trains a cost-specific model, it
  becomes another `AIProvider` implementation (e.g., `MCAICDProvider`).
  The domain service is unchanged.
- **Provider registry:** As the provider count grows, move from a static
  `_PROVIDER_MAP` to an entry-point-based plugin system (`importlib.metadata`)
  so third parties can ship providers without forking the core.
- **Gateway integration:** If a gateway (LiteLLM) is adopted for
  observability and routing, each `Provider` implementation becomes a thin
  wrapper around the gateway's unified client. The protocol remains the
  same.

---

## References

- [ADR-0001: FastAPI](../adr/ADR-0001-fastapi.md) — the async framework that enables the async protocol
- [ADR-0003: Clean Architecture](../adr/ADR-0003-clean-architecture.md) — the layering that isolates the protocol in the domain layer
- [LiteLLM Documentation](https://docs.litellm.ai/) — candidate gateway for multi-provider routing
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)
- [Google Gemini API Reference](https://ai.google.dev/api)
- [Anthropic Claude API Reference](https://docs.anthropic.com/claude/reference)
- [Azure OpenAI Service Documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/)
