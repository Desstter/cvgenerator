def combined_analyze_adapt_prompt(cv_json: str, job_text: str, real_context: str = "") -> str:
    context_block = ""
    if real_context:
        context_block = f"""
REAL CONTEXT (for intelligent technology substitutions):
{real_context}

TIERED SUBSTITUTION (goal: embellish believably, NOT chase keywords):
- TIER 1 (adjacent/transferable, e.g. React↔Vue, Node↔Django): reframe real work as the job's tech, keep achievements/metrics intact.
- TIER 2 (foreign tech with no real basis, e.g. Ruby on Rails when never used): DO NOT claim it, DO NOT build the CV around "looking to apply X". Surface a genuine adjacency at most, never name it as owned experience.
- ADDITIVE, NOT SUBTRACTIVE: if the candidate has both a real differentiator and the job's tech (e.g. OCI + AWS), keep BOTH and reorder — never delete a real skill to insert the job's keyword.
TONE: assert ("I built/led"), never aspire ("looking to/eager to"). Every claim must survive an interview.
"""

    return f"""Perform two tasks in a single response:

TASK 1 — ANALYZE the job description and return structured data.
TASK 2 — ADAPT the CV to match the job description.

Return a JSON object with exactly two keys: "job_analysis" and "adapted_cv".

JOB ANALYSIS fields (extract from the job description):
- title: job title
- company: company name (empty string if not mentioned)
- required_skills: must-have technical skills
- preferred_skills: nice-to-have skills
- keywords: other important keywords
- responsibilities: main responsibilities list
- detected_language: "en" or "es"

CV ADAPTATION RULES:
- NEVER change: company names, dates, education, contact info
- REWRITE: summary and experience descriptions to highlight relevant skills
- ADAPT: job titles per company to match the target role — realistic role names only, NEVER tag the job's buzzword onto the title (FORBIDDEN: "Frontend Engineer (AI-Assisted)")
- REORDER: skills list with most relevant first
- SUBSTITUTE: technologies to match job requirements (see real context)
- LANGUAGE: Write the entire adapted CV in the SAME language as the job description
- Start bullet points with strong action verbs (Led, Built, Implemented, Optimized, Delivered)
- Integrate the job's keywords naturally into real accomplishments — never as decoration
- Quantify achievements where the original implies measurable results
- ANTI-STUFFING: never reuse the same job-description phrase across more than one bullet; do not prepend the job's headline term to every bullet ("AI-driven X, AI-driven Y..."); one truthful, in-context mention of a keyword scores the same with an ATS as five — prefer it. If a keyword can't be placed truthfully, leave it out.
{context_block}
DATA TYPE REQUIREMENTS (critical):
- All "description" fields must be STRINGS with newline-separated bullets, NOT arrays
- "summary" must be a STRING, NOT an array

Current CV:
{cv_json}

Job Description:
{job_text}"""


def job_analysis_prompt(job_text: str) -> str:
    return f"""Analyze this job description and extract structured information.
Also detect the language of this job description (return "es" for Spanish, "en" for English).

Return ONLY valid JSON:
{{
  "title": "job title",
  "company": "company name",
  "required_skills": ["skill1", "skill2"],
  "preferred_skills": ["skill1", "skill2"],
  "keywords": ["keyword1", "keyword2"],
  "responsibilities": ["resp1", "resp2"],
  "detected_language": "en"
}}

Job Description:
{job_text}"""


def full_cv_adaptation_prompt(cv_json: str, job_json: str, real_context: str = "") -> str:
    context_block = ""
    if real_context:
        context_block = f"""
REAL CONTEXT (use this to make intelligent, TIERED technology substitutions):
{real_context}

TIER 1 — ADJACENT/TRANSFERABLE (React↔Vue, Node↔Django): reframe the real work as the job's tech,
keep the real achievements/scope/metrics intact. e.g. Vue.js at Grupo Vidawa → describe as React.
TIER 2 — FOREIGN tech with no real basis (e.g. Ruby on Rails, never used): DO NOT claim it and DO NOT
build the summary/bullets around "looking to apply X". Surface a genuine adjacency at most, never as owned experience.
ADDITIVE, NOT SUBTRACTIVE: if the candidate has both a real differentiator and the job's tech (e.g. OCI + AWS),
keep BOTH and just reorder (job's tech first) — never delete a real skill to insert the job's keyword.
TONE: assert ("built/led"), never aspire ("looking to/eager to"). Every claim must survive an interview.
"""

    return f"""Adapt the following CV to better match the job description.

IMPORTANT RULES:
- NEVER change: company names, dates, education institutions, degree names, contact info
- YOU CAN change: job titles per company to better match the target role
- REWRITE: summary, experience descriptions, project descriptions to highlight relevant skills
- REORDER: skills list so matching skills come first
- SUBSTITUTE: technologies to match job requirements (see real context below)
- LANGUAGE: Output the CV in the SAME language as the job description
- Start bullet points with action verbs
- Integrate the job's keywords naturally into real accomplishments — never as decoration
- ANTI-STUFFING: never reuse the same phrase across more than one bullet; do not prepend the job's headline term to every bullet; one truthful mention scores the same with an ATS as five. If a keyword can't be placed truthfully, leave it out.
- ADAPT job titles to realistic role names only — never tag the job's buzzword onto the title
- Quantify achievements where possible
{context_block}
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
TONE: assert competence ("I build/lead"), never aspire ("looking to apply / eager to learn X"). Don't build the summary around a skill the candidate lacks.

Original summary:
{current_summary}

Return ONLY the rewritten summary text, no JSON, no quotes."""


def experience_prompt(experience_json: str, job_keywords: list[str], language: str) -> str:
    kw_str = ", ".join(job_keywords)
    lang_note = "Write in Spanish." if language == "es" else "Write in English."
    return f"""Rewrite the description bullets for this experience entry to better match a role requiring: {kw_str}

{lang_note}
RULES:
- NEVER change: company, dates, location
- You CAN change the job title to better match the target role
- Rewrite description bullets using action verbs and relevant keywords
- Quantify achievements where the original implies measurable results
- Keep the same number of bullets (or fewer)
- TIERED tech substitution: reframe only adjacent/transferable tech (React↔Vue, Node↔Django); do NOT claim foreign tech with no real basis, and do NOT frame bullets as "looking to apply X"
- ADDITIVE, not subtractive: keep the candidate's real differentiator techs, just reorder the job's tech first — never delete a real skill
- TONE: assert what was done, never aspire

Experience entry:
{experience_json}

Return ONLY valid JSON with the same structure, only title, description and technologies fields changed."""
