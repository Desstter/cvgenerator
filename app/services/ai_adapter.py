import json
import re
import time
import logging
from abc import ABC, abstractmethod
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from app.config import settings
from app.services.event_log import log_event
from app.models.schemas import CVData, JobDescription, ExperienceEntry, ProjectEntry, SkillCategory
from app.prompts.system_prompt import SYSTEM_PROMPT, get_system_prompt
from app.prompts.section_prompts import (
    job_analysis_prompt,
    full_cv_adaptation_prompt,
    combined_analyze_adapt_prompt,
    refine_cv_prompt,
)
from app.services.cv_analyzer import build_ai_parse_prompt, parse_ai_response_to_cv

logger = logging.getLogger(__name__)


def _str_list() -> dict:
    return {"type": "array", "items": {"type": "string"}}


# Strict JSON schema for the combined analyze+adapt call. Used natively by providers
# with structured-output support (Claude); others rely on the prompt + json-repair.
ANALYZE_ADAPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "job_analysis": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "company": {"type": "string"},
                "required_skills": _str_list(),
                "preferred_skills": _str_list(),
                "keywords": _str_list(),
                "responsibilities": _str_list(),
                "detected_language": {"type": "string", "enum": ["en", "es"]},
            },
            "required": ["title", "company", "required_skills", "preferred_skills",
                         "keywords", "responsibilities", "detected_language"],
        },
        "keyword_equivalences": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"term": {"type": "string"}, "equivalents": _str_list()},
                "required": ["term", "equivalents"],
            },
        },
        "adapted_cv": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "skills": _str_list(),
                "skill_categories": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"name": {"type": "string"}, "skills": _str_list()},
                        "required": ["name", "skills"],
                    },
                },
                "experience": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "technologies": _str_list(),
                        },
                        "required": ["title", "description", "technologies"],
                    },
                },
                "projects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "description": {"type": "string"},
                            "technologies": _str_list(),
                        },
                        "required": ["description", "technologies"],
                    },
                },
            },
            "required": ["summary", "skills", "skill_categories", "experience", "projects"],
        },
    },
    "required": ["job_analysis", "keyword_equivalences", "adapted_cv"],
}

REFINE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"description": {"type": "string"}},
                "required": ["description"],
            },
        },
        "projects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"description": {"type": "string"}},
                "required": ["description"],
            },
        },
    },
    "required": ["summary", "experience", "projects"],
}


def _log_before_sleep(retry_state) -> None:
    """Tenacity hook: surface every retry (attempt, wait, cause) in the event log."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    wait = getattr(retry_state.next_action, "sleep", 0) or 0
    log_event(
        "retry",
        f"Attempt {retry_state.attempt_number} failed ({type(exc).__name__}: {exc}) — "
        f"retrying in {wait:.1f}s",
        level="retry",
    )


def _is_retryable_error(exception: Exception) -> bool:
    """Determine if an exception is transient and should be retried."""
    exc_name = exception.__class__.__name__

    if exc_name in ['AuthenticationError', 'PermissionDeniedError', 'Unauthorized']:
        logger.warning(f"Not retrying {exc_name}: {exception}")
        return False

    if exc_name in ['InvalidRequestError', 'BadRequestError', 'ValidationError']:
        logger.warning(f"Not retrying {exc_name}: {exception}")
        return False

    if exc_name in ['APIConnectionError', 'APITimeoutError', 'RateLimitError',
                    'InternalServerError', 'ServiceUnavailableError',
                    'ConnectionError', 'Timeout', 'ReadTimeout',
                    # google.api_core exceptions (Gemini)
                    'ResourceExhausted', 'ServiceUnavailable', 'DeadlineExceeded',
                    'TooManyRequests', 'Aborted']:
        logger.info(f"Retrying {exc_name}: {exception}")
        return True

    status = getattr(exception, 'status_code', None) or getattr(exception, 'code', None)
    if isinstance(status, int):
        if status == 429 or (500 <= status < 600):
            logger.info(f"Retrying HTTP {status}: {exception}")
            return True
        if 400 <= status < 500:
            logger.warning(f"Not retrying HTTP {status}: {exception}")
            return False

    logger.warning(f"Not retrying unknown error {exc_name}: {exception}")
    return False


class AIProvider(ABC):
    @abstractmethod
    def chat(self, system: str, user: str) -> str: ...

    def chat_json(self, system: str, user: str, schema=None) -> dict:
        """Call chat() and parse JSON. Override in providers that support native structured output."""
        response = self.chat(system, user)
        return json.loads(_extract_json(response))


class _APICall:
    """Context manager that logs an outgoing API request and its outcome."""

    def __init__(self, provider: str, model: str, prompt_chars: int, mode: str = "chat"):
        self.label = f"{provider} · {model}"
        self.prompt_chars = prompt_chars
        self.mode = mode
        self.start = 0.0

    def __enter__(self):
        log_event(
            "api",
            f"→ {self.label} [{self.mode}] request ({self.prompt_chars:,} prompt chars)",
            level="api",
        )
        self.start = time.perf_counter()
        return self

    def done(self, response_chars: int):
        elapsed = time.perf_counter() - self.start
        log_event(
            "api",
            f"← {self.label} OK in {elapsed:.1f}s ({response_chars:,} response chars)",
            level="success",
        )

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            elapsed = time.perf_counter() - self.start
            log_event(
                "api",
                f"✗ {self.label} failed after {elapsed:.1f}s — {exc_type.__name__}: {exc}",
                level="error",
            )
        return False


class ClaudeProvider(AIProvider):
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model
        self.config = settings
        self.anthropic = anthropic

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=_log_before_sleep,
        reraise=True
    )
    def chat(self, system: str, user: str) -> str:
        with _APICall("Claude", self.model, len(system) + len(user)) as call:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.config.claude_max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = next(b.text for b in response.content if b.type == "text")
            call.done(len(text))
            return text

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=_log_before_sleep,
        reraise=True
    )
    def chat_json(self, system: str, user: str, schema=None) -> dict:
        """Use native structured outputs: the API guarantees the response matches the schema."""
        if schema is None:
            return super().chat_json(system, user)
        with _APICall("Claude", self.model, len(system) + len(user), mode="json_schema") as call:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.config.claude_max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
            text = next(b.text for b in response.content if b.type == "text")
            call.done(len(text))
            return json.loads(text)


class OpenAIProvider(AIProvider):
    def __init__(self):
        import openai
        self.client = openai.OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.config = settings
        self.openai = openai

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=_log_before_sleep,
        reraise=True
    )
    def chat(self, system: str, user: str) -> str:
        with _APICall("OpenAI", self.model, len(system) + len(user)) as call:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=self.config.openai_max_tokens,
            )
            text = response.choices[0].message.content
            call.done(len(text or ""))
            return text

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=_log_before_sleep,
        reraise=True
    )
    def chat_json(self, system: str, user: str, schema=None) -> dict:
        """Use OpenAI JSON mode so the response is guaranteed to be valid JSON."""
        with _APICall("OpenAI", self.model, len(system) + len(user), mode="json") as call:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=self.config.openai_max_tokens,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content
            call.done(len(text or ""))
            return json.loads(text)


class GeminiProvider(AIProvider):
    def __init__(self):
        import google.generativeai as genai
        genai.configure(api_key=settings.google_api_key)
        self.genai = genai
        self.config = settings
        # dict.fromkeys dedupes while preserving order (env primary may repeat a fallback)
        self._models = list(dict.fromkeys([settings.gemini_model] + settings.gemini_fallback_models))

    # Errors that justify trying the next model in the fallback chain instead of
    # aborting: quota/rate limits, missing models, and transient server overload.
    _FALLBACK_KEYWORDS = (
        "quota", "429", "rate", "resource", "not found", "404",
        "503", "500", "overload", "unavailable", "internal", "deadline", "timeout",
    )

    def _make_model(self, model_name: str, system: str):
        return self.genai.GenerativeModel(model_name, system_instruction=system)

    def _generate(self, model_name: str, system: str, prompt: str, generation_config: dict):
        model = self._make_model(model_name, system)
        return model.generate_content(
            prompt,
            generation_config=generation_config,
            request_options={"timeout": 120},
        )

    def _run_with_fallback(self, system: str, prompt: str, generation_config: dict) -> str:
        last_error = None
        for model_name in self._models:
            with _APICall("Gemini", model_name, len(prompt),
                          mode=generation_config.get("response_mime_type", "chat")) as call:
                try:
                    response = self._generate(model_name, system, prompt, generation_config)
                    text = response.text
                    call.done(len(text))
                    logger.info(f"Gemini response from: {model_name}")
                    return text
                except Exception as e:
                    err_msg = str(e).lower()
                    if any(k in err_msg for k in self._FALLBACK_KEYWORDS):
                        log_event(
                            "api",
                            f"Gemini {model_name} unavailable ({type(e).__name__}: {e}) — "
                            f"falling back to next model",
                            level="warn",
                        )
                        last_error = e
                        continue
                    raise
        log_event("api", "All Gemini models exhausted — giving up", level="error")
        raise last_error

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=2, max=8),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=_log_before_sleep,
        reraise=True,
    )
    def _run_with_retry(self, system: str, prompt: str, generation_config: dict) -> str:
        return self._run_with_fallback(system, prompt, generation_config)

    def chat(self, system: str, user: str) -> str:
        return self._run_with_retry(
            system, user, {"max_output_tokens": self.config.gemini_max_tokens}
        )

    def chat_json(self, system: str, user: str, schema=None) -> dict:
        # NOTE: response_schema is intentionally NOT used. On gemini-2.5-flash-lite
        # (google-generativeai 0.8.4) it triggers degenerate output (repetition
        # loops or near-empty responses). response_mime_type + the explicit JSON
        # structure in the prompt produces complete, valid output instead.
        config = {
            "max_output_tokens": self.config.gemini_max_tokens,
            "response_mime_type": "application/json",
        }
        text = self._run_with_retry(system, user, config)
        return json.loads(_extract_json(text))


def get_provider(name: str | None = None) -> AIProvider:
    provider_name = (name or settings.ai_provider).lower()
    if provider_name == "claude":
        provider = ClaudeProvider()
        model = settings.claude_model
    elif provider_name == "openai":
        provider = OpenAIProvider()
        model = settings.openai_model
    elif provider_name == "gemini":
        provider = GeminiProvider()
        model = " → ".join(provider._models)
    else:
        log_event("provider", f"Unknown AI provider requested: {provider_name}", level="error")
        raise ValueError(f"Unknown AI provider: {provider_name}")
    log_event("provider", f"Provider: {provider_name} ({model})")
    return provider


def _repair_json(candidate: str) -> str | None:
    """Try to repair malformed JSON using json-repair. Returns fixed string or None."""
    try:
        from json_repair import repair_json
        repaired = repair_json(candidate)
        if repaired and repaired not in ('""', "''", "null"):
            json.loads(repaired)  # validate the repair actually worked
            return repaired
    except Exception:
        pass
    return None


def _extract_json(text: str) -> str:
    """Extract JSON from AI response with validation and robust parsing."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            repaired = _repair_json(candidate)
            if repaired:
                log_event(
                    "json", "Fenced JSON block was malformed; recovered via json-repair "
                    "(response may be truncated — check the raw text)",
                    level="warn", detail=candidate,
                )
                return repaired

    brace_count = 0
    start_idx = text.find('{')
    if start_idx == -1:
        return text

    for i in range(start_idx, len(text)):
        if text[i] == '{':
            brace_count += 1
        elif text[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                candidate = text[start_idx:i+1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    continue

    # Last resort: repair the whole text (handles truncated/malformed responses)
    repaired = _repair_json(text)
    if repaired:
        log_event(
            "json", "JSON was malformed; recovered via json-repair "
            "(response may be truncated — fields lost this way silently fall back to the original CV)",
            level="warn", detail=text,
        )
        return repaired

    return text


def _strip_markdown(obj):
    """Recursively strip markdown formatting (**bold**, *italic*, etc.) from strings."""
    if isinstance(obj, dict):
        return {k: _strip_markdown(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_strip_markdown(item) for item in obj]
    elif isinstance(obj, str):
        # Remove bold **text** and __text__
        obj = re.sub(r'\*\*(.+?)\*\*', r'\1', obj)
        obj = re.sub(r'__(.+?)__', r'\1', obj)
        # Remove italic *text* and _text_ (but not underscores in tech names)
        obj = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'\1', obj)
        return obj
    return obj


def _clean_none_values(obj):
    """Recursively convert None values to empty strings or empty lists."""
    if isinstance(obj, dict):
        return {k: _clean_none_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_none_values(item) for item in obj]
    elif obj is None:
        return ""
    return obj


def _coerce_equivalences(raw) -> dict[str, list[str]]:
    """Validate the LLM's keyword_equivalences. Drop anything malformed instead of raising.

    Accepts both the list-of-objects format ([{"term": ..., "equivalents": [...]}]) and the
    legacy dict format ({"term": [...]}).
    """
    if isinstance(raw, list):
        converted = {}
        for item in raw:
            if isinstance(item, dict) and "term" in item:
                converted[item["term"]] = item.get("equivalents", [])
        raw = converted
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, list[str]] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not k.strip():
            continue
        if isinstance(v, list):
            equivalents = [str(item).strip() for item in v if isinstance(item, (str, int, float)) and str(item).strip()]
        elif isinstance(v, str) and v.strip():
            equivalents = [v.strip()]
        else:
            continue
        if equivalents:
            cleaned[k.strip()] = equivalents
    return cleaned


def analyze_and_adapt(
    provider: AIProvider,
    cv: CVData,
    job_text: str,
    real_context: str = "",
    profile_type: str = "developer",
) -> tuple[JobDescription, CVData, dict[str, list[str]]]:
    """Single API call: analyze job description and adapt the CV simultaneously.

    Returns (job, adapted_cv, keyword_equivalences). The equivalences map is the LLM's
    suggested synonym pairs used downstream by ATS scoring to avoid false negatives.
    """
    cv_dict = cv.model_dump(exclude={"raw_markdown"})
    prompt = combined_analyze_adapt_prompt(
        json.dumps(cv_dict, ensure_ascii=False, indent=2),
        job_text,
        real_context=real_context,
        profile_type=profile_type,
    )

    data = provider.chat_json(get_system_prompt(profile_type), prompt, schema=ANALYZE_ADAPT_SCHEMA)
    data = _clean_none_values(data)
    data = _strip_markdown(data)

    job_data = data.get("job_analysis", {})
    job = JobDescription(
        raw_text=job_text,
        title=job_data.get("title", ""),
        company=job_data.get("company", ""),
        required_skills=job_data.get("required_skills", []),
        preferred_skills=job_data.get("preferred_skills", []),
        keywords=job_data.get("keywords", []),
        responsibilities=job_data.get("responsibilities", []),
        detected_language=job_data.get("detected_language", "en"),
    )

    if not (job.required_skills or job.preferred_skills or job.keywords):
        # Without keywords every ATS score is 0/0 — a silent, useless result.
        # Fail loudly instead; the raw response is in the activity log.
        raise ValueError(
            "Job analysis extracted no skills or keywords — the AI response was likely "
            "truncated or malformed. Check the JSON warnings in the activity log and retry."
        )

    equivalences = _coerce_equivalences(data.get("keyword_equivalences"))

    cv_data = data.get("adapted_cv", {})
    detected_lang = "en" if profile_type == "bpo" else (job.detected_language or cv.detected_language)

    skill_categories = []
    for cat in cv_data.get("skill_categories", []):
        if isinstance(cat, dict) and cat.get("name") and isinstance(cat.get("skills"), list):
            skill_categories.append(SkillCategory(
                name=str(cat["name"]),
                skills=[str(s) for s in cat["skills"] if s],
            ))

    adapted = CVData(
        contact=cv.contact,
        headline=cv.headline,
        summary=cv_data.get("summary", cv.summary),
        experience=[],
        education=cv.education,
        skills=cv_data.get("skills", cv.skills),
        skill_categories=skill_categories,
        certifications=cv.certifications,
        languages=cv.languages,
        raw_markdown=cv.raw_markdown,
        detected_language=detected_lang,
    )

    adapted_experiences = cv_data.get("experience", [])
    for i, orig in enumerate(cv.experience):
        if i < len(adapted_experiences):
            ae = adapted_experiences[i]
            adapted.experience.append(ExperienceEntry(
                company=orig.company,
                title=orig.title,
                dates=orig.dates,
                location=orig.location,
                description=ae.get("description", orig.description),
                technologies=orig.technologies,
            ))
        else:
            adapted.experience.append(orig)

    adapted_projects = cv_data.get("projects", [])
    for i, orig in enumerate(cv.projects):
        if i < len(adapted_projects):
            ap = adapted_projects[i]
            adapted.projects.append(ProjectEntry(
                name=orig.name,
                url=orig.url,
                description=ap.get("description", orig.description),
                technologies=ap.get("technologies", orig.technologies),
            ))
        else:
            adapted.projects.append(orig)

    return job, adapted, equivalences


def refine_cv(
    provider: AIProvider,
    adapted: CVData,
    job: JobDescription,
    profile_type: str = "developer",
) -> CVData:
    """Second AI pass: critique the adapted CV as a senior recruiter and rewrite weak parts.

    Only summary and descriptions may change; structure, titles, and technologies are preserved.
    Any failure returns the input CV unchanged — this pass must never break the pipeline.
    """
    try:
        cv_dict = adapted.model_dump(
            include={"summary": True, "experience": True, "projects": True}
        )
        prompt = refine_cv_prompt(
            json.dumps(cv_dict, ensure_ascii=False, indent=2),
            job_title=job.title or "the target role",
            job_skills=job.required_skills + job.preferred_skills,
            language=job.detected_language,
            profile_type=profile_type,
        )
        data = provider.chat_json(get_system_prompt(profile_type), prompt, schema=REFINE_SCHEMA)
        data = _strip_markdown(_clean_none_values(data))

        refined = adapted.model_copy(deep=True)
        if isinstance(data.get("summary"), str) and data["summary"].strip():
            refined.summary = data["summary"].strip()

        refined_exp = data.get("experience", [])
        if isinstance(refined_exp, list) and len(refined_exp) == len(refined.experience):
            for entry, new in zip(refined.experience, refined_exp):
                desc = new.get("description") if isinstance(new, dict) else None
                if isinstance(desc, str) and desc.strip():
                    entry.description = desc.strip()

        refined_proj = data.get("projects", [])
        if isinstance(refined_proj, list) and len(refined_proj) == len(refined.projects):
            for entry, new in zip(refined.projects, refined_proj):
                desc = new.get("description") if isinstance(new, dict) else None
                if isinstance(desc, str) and desc.strip():
                    entry.description = desc.strip()

        logger.info("Refine pass applied")
        return refined
    except Exception:
        logger.exception("Refine pass failed; keeping first-pass CV")
        return adapted


def analyze_job(provider: AIProvider, job_text: str) -> JobDescription:
    """Use AI to parse a job description into structured data."""
    prompt = job_analysis_prompt(job_text)
    response = provider.chat(SYSTEM_PROMPT, prompt)
    json_str = _extract_json(response)
    data = json.loads(json_str)
    data = _clean_none_values(data)
    return JobDescription(
        raw_text=job_text,
        title=data.get("title", ""),
        company=data.get("company", ""),
        required_skills=data.get("required_skills", []),
        preferred_skills=data.get("preferred_skills", []),
        keywords=data.get("keywords", []),
        responsibilities=data.get("responsibilities", []),
        detected_language=data.get("detected_language", "en"),
    )


def parse_cv_with_ai(provider: AIProvider, markdown: str) -> CVData:
    """Use AI to parse CV markdown when rule-based parsing is insufficient."""
    prompt = build_ai_parse_prompt(markdown)
    response = provider.chat(SYSTEM_PROMPT, prompt)
    return parse_ai_response_to_cv(response, markdown)


def adapt_cv(provider: AIProvider, cv: CVData, job: JobDescription, real_context: str = "") -> CVData:
    """Full CV adaptation: sends CV + job to AI, returns adapted CVData."""
    cv_dict = cv.model_dump(exclude={"raw_markdown"})
    job_dict = job.model_dump(exclude={"raw_text"})

    prompt = full_cv_adaptation_prompt(
        json.dumps(cv_dict, ensure_ascii=False, indent=2),
        json.dumps(job_dict, ensure_ascii=False, indent=2),
        real_context=real_context,
    )

    response = provider.chat(SYSTEM_PROMPT, prompt)
    json_str = _extract_json(response)
    data = json.loads(json_str)
    data = _clean_none_values(data)
    data = _strip_markdown(data)

    # Detect language from job description
    detected_lang = job.detected_language or cv.detected_language

    # Build adapted CV, preserving immutable fields from original
    adapted = CVData(
        contact=cv.contact,  # Never change contact info
        headline=cv.headline,
        summary=data.get("summary", cv.summary),
        experience=[],
        education=cv.education,  # Never change education
        skills=data.get("skills", cv.skills),
        certifications=cv.certifications,
        languages=cv.languages,
        raw_markdown=cv.raw_markdown,
        detected_language=detected_lang,
    )

    # For experience: preserve company/dates/location, allow title changes
    adapted_experiences = data.get("experience", [])
    for i, orig in enumerate(cv.experience):
        if i < len(adapted_experiences):
            ae = adapted_experiences[i]
            adapted.experience.append(ExperienceEntry(
                company=orig.company,
                title=ae.get("title", orig.title),  # Allow title adaptation
                dates=orig.dates,
                location=orig.location,
                description=ae.get("description", orig.description),
                technologies=ae.get("technologies", orig.technologies),
            ))
        else:
            adapted.experience.append(orig)

    # Projects - preserve name, update description
    adapted_projects = data.get("projects", [])
    for i, orig in enumerate(cv.projects):
        if i < len(adapted_projects):
            ap = adapted_projects[i]
            adapted.projects.append(ProjectEntry(
                name=orig.name,
                url=orig.url,
                description=ap.get("description", orig.description),
                technologies=ap.get("technologies", orig.technologies),
            ))
        else:
            adapted.projects.append(orig)

    return adapted
