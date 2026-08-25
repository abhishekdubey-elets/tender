"""The EventExtractionService: normalized document → validated events."""
from __future__ import annotations

import hashlib
from collections.abc import Callable, MutableMapping
from datetime import datetime, timezone

from pydantic import ValidationError

from app.extraction.grounding import find_ungrounded, strip_ungrounded
from app.extraction.llm import LLMClient, LLMError
from app.extraction.prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.extraction.schema import EventExtractionEnvelope, envelope_json_schema
from app.extraction.types import ExtractionResult, ExtractionRunMeta, ExtractionStatus
from app.processing.types import NormalizedDocument

PROVIDER = "anthropic"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventExtractionService:
    def __init__(
        self,
        llm: LLMClient,
        *,
        model: str = "claude-opus-5",
        max_attempts: int = 3,
        require_grounded_evidence: bool = True,
        cache: MutableMapping[str, ExtractionResult] | None = None,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._llm = llm
        self._model = model
        self._max_attempts = max(1, max_attempts)
        self._require_grounded = require_grounded_evidence
        self._cache = cache
        self._now = now
        self._schema = envelope_json_schema()

    def _cache_key(self, input_sha: str) -> str:
        return f"{self._model}|{PROMPT_VERSION}|{input_sha}"

    def extract(self, document: NormalizedDocument) -> ExtractionResult:
        text = document.text
        requested_at = self._now()

        # Nothing to extract (empty, or scanned/OCR-pending).
        if not text or not text.strip():
            return ExtractionResult(
                status=ExtractionStatus.skipped,
                events=[],
                meta=ExtractionRunMeta(
                    provider=PROVIDER, model=self._model, prompt_version=PROMPT_VERSION,
                    requested_at=requested_at, completed_at=self._now(), attempts=0,
                ),
                warnings=["no extractable text"],
            )

        input_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

        # Cache → deterministic reuse for identical (model, prompt, input).
        if self._cache is not None:
            hit = self._cache.get(self._cache_key(input_sha))
            if hit is not None:
                cached = ExtractionResult(
                    status=hit.status, events=hit.events,
                    meta=ExtractionRunMeta(
                        provider=hit.meta.provider, model=hit.meta.model,
                        prompt_version=hit.meta.prompt_version, requested_at=requested_at,
                        completed_at=self._now(), attempts=hit.meta.attempts,
                        input_tokens=hit.meta.input_tokens, output_tokens=hit.meta.output_tokens,
                        from_cache=True,
                    ),
                    input_sha256=input_sha, warnings=list(hit.warnings),
                )
                return cached

        corrective: str | None = None
        last_error: str | None = None
        attempts = 0
        in_tok = out_tok = None
        used_model = self._model

        while attempts < self._max_attempts:
            attempts += 1
            user = build_user_prompt(text, source_url=document.source_url, corrective=corrective)
            try:
                resp = self._llm.complete_structured(
                    system=SYSTEM_PROMPT, user=user, schema=self._schema, model=self._model
                )
            except LLMError as exc:
                last_error = f"llm_error: {exc}"
                continue

            in_tok, out_tok, used_model = resp.input_tokens, resp.output_tokens, resp.model

            try:
                envelope = EventExtractionEnvelope.model_validate(resp.data)
            except ValidationError as exc:
                last_error = f"schema_validation: {exc}"
                corrective = (
                    "Your previous output failed schema validation. Return ONLY valid JSON "
                    f"matching the schema. Errors: {exc}"
                )
                continue

            ungrounded = find_ungrounded(envelope, text)
            if ungrounded and self._require_grounded and attempts < self._max_attempts:
                last_error = f"ungrounded_evidence: {len(ungrounded)} snippet(s)"
                sample = "; ".join(s for _i, s in ungrounded[:5])
                corrective = (
                    "Some evidence snippets were NOT found verbatim in the document and are "
                    f"not allowed: [{sample}]. Only include snippets copied EXACTLY from the "
                    "document, and never invent facts."
                )
                continue

            warnings: list[str] = []
            if ungrounded:
                removed = strip_ungrounded(envelope, text)
                warnings.append(f"stripped {removed} ungrounded evidence snippet(s)")

            result = ExtractionResult(
                status=ExtractionStatus.succeeded,
                events=envelope.events,
                meta=ExtractionRunMeta(
                    provider=PROVIDER, model=used_model, prompt_version=PROMPT_VERSION,
                    requested_at=requested_at, completed_at=self._now(), attempts=attempts,
                    input_tokens=in_tok, output_tokens=out_tok,
                ),
                input_sha256=input_sha, warnings=warnings,
            )
            if self._cache is not None:
                self._cache[self._cache_key(input_sha)] = result
            return result

        # Retries exhausted.
        return ExtractionResult(
            status=ExtractionStatus.failed,
            events=[],
            meta=ExtractionRunMeta(
                provider=PROVIDER, model=used_model, prompt_version=PROMPT_VERSION,
                requested_at=requested_at, completed_at=self._now(), attempts=attempts,
                input_tokens=in_tok, output_tokens=out_tok,
            ),
            input_sha256=input_sha, error=last_error,
        )
