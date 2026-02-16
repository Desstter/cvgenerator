def job_analysis_prompt(job_text: str) -> str:
    return f"""Analyze this job description and extract structured information.
Return ONLY valid JSON:
{{
  "title": "job title",
  "company": "company name",
  "required_skills": ["skill1", "skill2"],
  "preferred_skills": ["skill1", "skill2"],
  "keywords": ["keyword1", "keyword2"],
  "responsibilities": ["resp1", "resp2"]
}}

Job Description:
{job_text}"""


def full_cv_adaptation_prompt(cv_json: str, job_json: str) -> str:
    return f"""Adapt the following CV to better match the job description.

IMPORTANT RULES:
- NEVER change: company names, job titles, dates, education institutions, degree names, contact info
- REWRITE: summary, experience descriptions, project descriptions to highlight relevant skills
- REORDER: skills list so matching skills come first
- Use the SAME language as the original CV
- Start bullet points with action verbs
- Mirror job description keywords where the candidate has matching experience
- Quantify achievements where possible
- Do NOT invent experience or skills not present in the original

Return ONLY valid JSON with the same structure as the input CV.

DATA TYPE REQUIREMENTS:
- "description" fields must be STRINGS (use newline-separated bullet points), NOT arrays
- "details" fields must be STRINGS, NOT arrays
- "summary" must be a STRING, NOT an array

Current CV:
{cv_json}

Target Job:
{job_json}"""


def summary_prompt(current_summary: str, job_keywords: list[str], language: str) -> str:
    kw_str = ", ".join(job_keywords)
    lang_note = "Write in Spanish." if language == "es" else "Write in English."
    return f"""Rewrite this professional summary to better target a role requiring: {kw_str}

{lang_note}
Keep it 2-4 sentences. Highlight relevant expertise. Use keywords from the job naturally.
Do NOT invent skills or experience not implied by the original.

Original summary:
{current_summary}

Return ONLY the rewritten summary text, no JSON, no quotes."""


def experience_prompt(experience_json: str, job_keywords: list[str], language: str) -> str:
    kw_str = ", ".join(job_keywords)
    lang_note = "Write in Spanish." if language == "es" else "Write in English."
    return f"""Rewrite the description bullets for this experience entry to better match a role requiring: {kw_str}

{lang_note}
RULES:
- NEVER change: company, title, dates, location
- Rewrite description bullets using action verbs and relevant keywords
- Quantify achievements where the original implies measurable results
- Keep the same number of bullets (or fewer)
- Only mention technologies the candidate actually used

Experience entry:
{experience_json}

Return ONLY valid JSON with the same structure, only description and technologies fields changed."""
