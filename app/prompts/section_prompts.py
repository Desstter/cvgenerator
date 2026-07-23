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

Return a JSON object with exactly three keys: "job_analysis", "adapted_cv", and "keyword_equivalences".

JOB ANALYSIS fields (extract from the job description):
- title: job title
- company: company name (empty string if not mentioned)
- required_skills: must-have technical skills
- preferred_skills: nice-to-have skills
- keywords: other important keywords
- responsibilities: main responsibilities list
- detected_language: "en" or "es"
- DEDUPLICATE: each skill/keyword must appear in exactly ONE of required_skills /
  preferred_skills / keywords (priority: required > preferred > keywords). Duplicates
  dilute the ATS score.
- required_skills = ONLY explicit must-haves ("required", "imprescindible", "must have").
  Anything phrased as a plus/bonus/nice-to-have goes in preferred_skills.

KEYWORD EQUIVALENCES (semantic enrichment for ATS scoring):
- Map each job keyword (required/preferred/general) to other terms in the CV that mean the same thing
  for this specific role, OR to terms the LLM knows are industry-equivalent.
- Format: a LIST of objects: [{{"term": "canonical_job_term", "equivalents": ["equivalent1", ...]}}]
- Examples: [{{"term": "React", "equivalents": ["ReactJS", "React.js"]}}, {{"term": "CI/CD pipelines", "equivalents": ["GitHub Actions", "Jenkins"]}}]
- ONLY include equivalences a recruiter would accept as the same thing. Do NOT stretch (e.g. do NOT
  map "Python" to "JavaScript"). When in doubt, leave it out — an empty list is valid.

CV ADAPTATION RULES:
- NEVER change: company names, dates, education, contact info
- SUMMARY ALIGNMENT: the summary's first sentence must present the candidate as the job's
  target role (use the job title's role wording naturally) + years + core stack.
- REWRITE: summary and experience descriptions following the BULLET QUALITY RULES and
  LENGTH AND STRUCTURE RULES from your instructions (formula, forbidden openers, quantification,
  bullet counts per role). These rules are the core of the task — a technically correct but
  generic rewrite is a failure.
- ADAPT: job titles per company to match the target role — realistic role names only, NEVER tag the job's buzzword onto the title (FORBIDDEN: "Frontend Engineer (AI-Assisted)")
- REORDER: skills list with most relevant first
- CATEGORIZE: group the skills into 3-5 named categories in "skill_categories" (e.g. Languages,
  Frameworks, Cloud & Infrastructure, Databases & Tools). Category names in the job's language.
  Every skill in "skills" must appear in exactly one category.
- SUBSTITUTE: technologies to match job requirements (see real context)
- LANGUAGE: Write the entire adapted CV in the SAME language as the job description
- ANTI-STUFFING: never reuse the same job-description phrase across more than one bullet; do not prepend the job's headline term to every bullet ("AI-driven X, AI-driven Y..."); one truthful, in-context mention of a keyword scores the same with an ATS as five — prefer it. If a keyword can't be placed truthfully, leave it out.
{context_block}
DATA TYPE REQUIREMENTS (critical):
- All "description" fields must be STRINGS with newline-separated bullets, NOT arrays
- "summary" must be a STRING, NOT an array
- "adapted_cv" must include: "summary", "skills", "skill_categories"
  (list of {{"name": "...", "skills": [...]}}), "experience" (list of
  {{"title": "...", "description": "...", "technologies": [...]}} in the SAME ORDER as the
  input CV), and "projects" (list of {{"description": "...", "technologies": [...]}} in the
  same order as the input CV)

Current CV:
{cv_json}

Job Description:
{job_text}"""


def refine_cv_prompt(adapted_cv_json: str, job_title: str, job_skills: list[str], language: str) -> str:
    """Second-pass critique: review the adapted CV as a senior recruiter and fix the weakest parts."""
    lang_note = "The CV must stay in Spanish." if language == "es" else "The CV must stay in English."
    skills_str = ", ".join(job_skills[:15])
    return f"""You are now acting as a SENIOR TECHNICAL RECRUITER reviewing this CV for a
"{job_title}" opening (key requirements: {skills_str}). You have 30 seconds per CV and you have
seen thousands. Be ruthless.

REVIEW PASS — find and FIX these problems:
1. WEAK BULLETS: any bullet violating the formula [action verb + specific what + measurable
   result/scope]. Rewrite it. If a bullet has no verifiable substance at all, cut it.
2. FORBIDDEN OPENERS: "Responsible for", "Helped", "Worked on", "Participated in" (or Spanish
   equivalents). Rewrite every occurrence.
3. VAGUE CLAIMS: "improved performance", "various technologies", "multiple projects" — replace
   with the specific system/number already present elsewhere in the CV, or cut the claim.
   NEVER invent new facts, numbers, employers, or technologies that are not already in the CV.
   KEYWORD GUARD: before cutting or rewriting a bullet, check if it contains a technology or
   requirement from the job ({skills_str}) that appears NOWHERE else in the CV descriptions.
   If so, keep that term in the rewritten text — rephrase around it, never drop it.
4. REDUNDANCY: two bullets saying the same thing → merge into the stronger one.
5. SUMMARY: if it exceeds 3 sentences or contains filler ("passionate", "results-driven",
   "motivated"), tighten it. First sentence = role + years + core stack.
6. BURIED LEDE: within each role, the bullet most relevant to "{job_title}" must come first.

{lang_note}
Keep everything that is already strong — do not rewrite for the sake of rewriting.
Do NOT change: titles, technologies lists, the number/order of experience entries, skills, or
skill_categories. Only "summary" and the "description" fields may change.

Return ONLY valid JSON with exactly this structure:
{{
  "summary": "refined summary string",
  "experience": [
    {{"description": "refined bullets as newline-separated STRING"}}
  ],
  "projects": [
    {{"description": "refined description STRING"}}
  ]
}}
"experience" and "projects" must have the SAME length and order as the input CV.

CV to review:
{adapted_cv_json}"""


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
