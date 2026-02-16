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
)
from app.services.cv_analyzer import build_ai_parse_prompt, parse_ai_response_to_cv

logger = logging.getLogger(__name__)


def _is_retryable_error(exception: Exception) -> bool:
    """Determine if an exception is transient and should be retried."""
    # Get the exception class name
    exc_name = exception.__class__.__name__

    # Don't retry authentication/authorization errors (permanent)
    if exc_name in ['AuthenticationError', 'PermissionDeniedError', 'Unauthorized']:
        logger.warning(f"Not retrying {exc_name}: {exception}")
        return False

    # Don't retry validation errors (permanent)
    if exc_name in ['InvalidRequestError', 'BadRequestError', 'ValidationError']:
        logger.warning(f"Not retrying {exc_name}: {exception}")
        return False

    # Retry connection errors, timeouts, rate limits, server errors (transient)
    if exc_name in ['APIConnectionError', 'APITimeoutError', 'RateLimitError',
                    'InternalServerError', 'ServiceUnavailableError',
                    'ConnectionError', 'Timeout', 'ReadTimeout']:
        logger.info(f"Retrying {exc_name}: {exception}")
        return True

    # For HTTP errors, check status code
    if hasattr(exception, 'status_code'):
        status = exception.status_code
        # Retry on 429 (rate limit), 500-599 (server errors)
        if status == 429 or (500 <= status < 600):
            logger.info(f"Retrying HTTP {status}: {exception}")
            return True
        # Don't retry 4xx client errors (except 429)
        if 400 <= status < 500:
            logger.warning(f"Not retrying HTTP {status}: {exception}")
            return False

    # For unknown errors, don't retry by default (safer)
    logger.warning(f"Not retrying unknown error {exc_name}: {exception}")
    return False


class AIProvider(ABC):
    @abstractmethod
    def chat(self, system: str, user: str) -> str:
        ...


class ClaudeProvider(AIProvider):
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model
        self.config = settings
        self.anthropic = anthropic  # Store module for exception types

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
        self.openai = openai  # Store module for exception types

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
        self.model = genai.GenerativeModel(
            settings.gemini_model,
            system_instruction=SYSTEM_PROMPT,
        )
        self.config = settings

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        reraise=True
    )
    def chat(self, system: str, user: str) -> str:
        # Gemini uses system_instruction at model level, so we prepend system context if different
        prompt = user if system == SYSTEM_PROMPT else f"{system}\n\n{user}"
        response = self.model.generate_content(
            prompt,
            generation_config={"max_output_tokens": self.config.gemini_max_tokens}
        )
        return response.text


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


def _extract_json(text: str) -> str:
    """Extract JSON from AI response with validation and robust parsing."""
    # Try markdown code block first
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)  # Validate it's valid JSON
            return candidate
        except json.JSONDecodeError:
            pass

    # Extract first complete JSON object using brace counting
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
                    json.loads(candidate)  # Validate before returning
                    return candidate
                except json.JSONDecodeError:
                    # Continue searching for next valid JSON object
                    continue

    return text  # Fallback to original text


def _clean_none_values(obj):
    """Recursively convert None values to empty strings or empty lists."""
    if isinstance(obj, dict):
        return {k: _clean_none_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_none_values(item) for item in obj]
    elif obj is None:
        return ""
    return obj


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
    )


def parse_cv_with_ai(provider: AIProvider, markdown: str) -> CVData:
    """Use AI to parse CV markdown when rule-based parsing is insufficient."""
    prompt = build_ai_parse_prompt(markdown)
    response = provider.chat(SYSTEM_PROMPT, prompt)
    return parse_ai_response_to_cv(response, markdown)


def adapt_cv(provider: AIProvider, cv: CVData, job: JobDescription) -> CVData:
    """Full CV adaptation: sends CV + job to AI, returns adapted CVData."""
    cv_dict = cv.model_dump(exclude={"raw_markdown"})
    job_dict = job.model_dump(exclude={"raw_text"})

    prompt = full_cv_adaptation_prompt(
        json.dumps(cv_dict, ensure_ascii=False, indent=2),
        json.dumps(job_dict, ensure_ascii=False, indent=2),
    )

    response = provider.chat(SYSTEM_PROMPT, prompt)
    json_str = _extract_json(response)
    data = json.loads(json_str)
    data = _clean_none_values(data)

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
        detected_language=cv.detected_language,
    )

    # For experience, preserve immutable fields
    adapted_experiences = data.get("experience", [])
    for i, orig in enumerate(cv.experience):
        if i < len(adapted_experiences):
            ae = adapted_experiences[i]
            adapted.experience.append(ExperienceEntry(
                company=orig.company,
                title=orig.title,
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
