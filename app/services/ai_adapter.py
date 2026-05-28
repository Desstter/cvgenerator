import json
import re
import logging
from abc import ABC, abstractmethod
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from app.config import settings
from app.models.schemas import CVData, JobDescription, ExperienceEntry, ProjectEntry
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.prompts.section_prompts import (
    job_analysis_prompt,
    full_cv_adaptation_prompt,
    combined_analyze_adapt_prompt,
)
from app.services.cv_analyzer import build_ai_parse_prompt, parse_ai_response_to_cv

logger = logging.getLogger(__name__)


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
                    'ConnectionError', 'Timeout', 'ReadTimeout']:
        logger.info(f"Retrying {exc_name}: {exception}")
        return True

    if hasattr(exception, 'status_code'):
        status = exception.status_code
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
        reraise=True
    )
    def chat(self, system: str, user: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.config.claude_max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text


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
        reraise=True
    )
    def chat(self, system: str, user: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=self.config.openai_max_tokens,
        )
        return response.choices[0].message.content


class GeminiProvider(AIProvider):
    def __init__(self):
        import google.generativeai as genai
        genai.configure(api_key=settings.google_api_key)
        self.genai = genai
        self.config = settings
        self._models = [settings.gemini_model] + settings.gemini_fallback_models

    def _make_model(self, model_name: str):
        return self.genai.GenerativeModel(model_name, system_instruction=SYSTEM_PROMPT)

    def _generate(self, model_name: str, prompt: str, generation_config: dict):
        model = self._make_model(model_name)
        return model.generate_content(prompt, generation_config=generation_config)

    def _run_with_fallback(self, prompt: str, generation_config: dict) -> str:
        last_error = None
        for model_name in self._models:
            try:
                response = self._generate(model_name, prompt, generation_config)
                logger.info(f"Gemini response from: {model_name}")
                return response.text
            except Exception as e:
                err_msg = str(e).lower()
                if any(k in err_msg for k in ("quota", "429", "rate", "resource", "not found", "404")):
                    logger.warning(f"Skipping {model_name}: {type(e).__name__}")
                    last_error = e
                    continue
                raise
        raise last_error

    def chat(self, system: str, user: str) -> str:
        prompt = user if system == SYSTEM_PROMPT else f"{system}\n\n{user}"
        return self._run_with_fallback(prompt, {"max_output_tokens": self.config.gemini_max_tokens})

    def chat_json(self, system: str, user: str, schema=None) -> dict:
        # NOTE: response_schema is intentionally NOT used. On gemini-2.5-flash-lite
        # (google-generativeai 0.8.4) it triggers degenerate output (repetition
        # loops or near-empty responses). response_mime_type + the explicit JSON
        # structure in the prompt produces complete, valid output instead.
        prompt = user if system == SYSTEM_PROMPT else f"{system}\n\n{user}"
        config = {
            "max_output_tokens": self.config.gemini_max_tokens,
            "response_mime_type": "application/json",
        }
        text = self._run_with_fallback(prompt, config)
        return json.loads(_extract_json(text))


def get_provider(name: str | None = None) -> AIProvider:
    provider_name = (name or settings.ai_provider).lower()
    if provider_name == "claude":
        return ClaudeProvider()
    elif provider_name == "openai":
        return OpenAIProvider()
    elif provider_name == "gemini":
        return GeminiProvider()
    else:
        raise ValueError(f"Unknown AI provider: {provider_name}")


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
        logger.warning("JSON was malformed; recovered via json-repair")
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
    """Validate the LLM's keyword_equivalences. Drop anything malformed instead of raising."""
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
    provider: AIProvider, cv: CVData, job_text: str, real_context: str = ""
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
    )

    data = provider.chat_json(SYSTEM_PROMPT, prompt)
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

    equivalences = _coerce_equivalences(data.get("keyword_equivalences"))

    cv_data = data.get("adapted_cv", {})
    detected_lang = job.detected_language or cv.detected_language

    adapted = CVData(
        contact=cv.contact,
        summary=cv_data.get("summary", cv.summary),
        experience=[],
        education=cv.education,
        skills=cv_data.get("skills", cv.skills),
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
                title=ae.get("title", orig.title),
                dates=orig.dates,
                location=orig.location,
                description=ae.get("description", orig.description),
                technologies=ae.get("technologies", orig.technologies),
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
