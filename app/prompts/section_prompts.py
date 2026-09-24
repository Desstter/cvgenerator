def combined_analyze_adapt_prompt(
    cv_json: str,
    job_text: str,
    real_context: str = "",
    profile_type: str = "developer",
) -> str:
    context_block = ""
    if real_context:
        context_block = f"""
REAL CONTEXT (verified evidence only):
{real_context}

EVIDENCE POLICY:
- Never substitute one technology for another, even when they are adjacent.
- Use only technologies, metrics and achievements present in the CV or this context.
- Keep the original skill inventory; relevance comes from ordering and truthful bullets.
TONE: assert ("I built/led"), never aspire ("looking to/eager to"). Every claim must survive an interview.
"""

    profile_rules = ""
    if profile_type == "bpo":
        profile_rules = """
BPO PROFILE OVERRIDES (higher priority than generic adaptation rules):
- Output the adapted CV in ENGLISH regardless of the job-description language.
- Preserve every original employment title exactly. Do not turn development roles into support roles.
- The summary may say "over three years of professional experience" but must NEVER imply years of customer-service/BPO experience.
- Only reorder or retain skills already present in the input CV. Do not introduce CRM, telephony, sales, billing, refund, retention, collections, or support-platform experience.
- Set every experience "technologies" list to the same value received in the input.
- Optimize for one page: summary <= 2 sentences; newest role <= 4 bullets; older roles <= 3 bullets; concise bullets.
- Emphasize verified transferable experience and leave unsupported job keywords out.
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
- NEVER change: company names, job titles, dates, education, contact info, per-role technologies, or the skill inventory
- SUMMARY ALIGNMENT: the summary's first sentence must present the candidate as the job's
  target role (use the job title's role wording naturally) + years + core stack.
- REWRITE: summary and experience descriptions following the BULLET QUALITY RULES and
  LENGTH AND STRUCTURE RULES from your instructions (formula, forbidden openers, quantification,
  bullet counts per role). These rules are the core of the task — a technically correct but
  generic rewrite is a failure.
- PRESERVE: every original job title and technology list exactly
- REORDER: verified skills with most relevant first; do not add or remove skills
- CATEGORIZE: group the skills into 3-5 named categories in "skill_categories" (e.g. Languages,
  Frameworks, Cloud & Infrastructure, Databases & Tools). Category names in the job's language.
  Every skill in "skills" must appear in exactly one category.
- LANGUAGE: Write the entire adapted CV in the SAME language as the job description
- ANTI-STUFFING: never reuse the same job-description phrase across more than one bullet; do not prepend the job's headline term to every bullet ("AI-driven X, AI-driven Y..."); one truthful, in-context mention of a keyword scores the same with an ATS as five — prefer it. If a keyword can't be placed truthfully, leave it out.
{context_block}
{profile_rules}
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


def refine_cv_prompt(
    adapted_cv_json: str,
    job_title: str,
    job_skills: list[str],
    language: str,
    profile_type: str = "developer",
) -> str:
    """Second-pass critique: review the adapted CV as a senior recruiter and fix the weakest parts."""
    lang_note = "The CV must stay in Spanish." if language == "es" else "The CV must stay in English."
    skills_str = ", ".join(job_skills[:15])
    if profile_type == "bpo":
        lang_note = "The CV must stay in English. The candidate has no direct call-center/BPO employment."
    bpo_guard = ""
    if profile_type == "bpo":
        bpo_guard = """
7. CAREER-CHANGE GUARD: preserve the exact job titles and never add direct BPO/call-center,
   CRM, telephony, sales, billing, refund, retention, ticket-volume, CSAT, AHT, or FCR claims.
   Keep the summary to two sentences and the full resume concise enough for one page.
"""
    return f"""You are now acting as a SENIOR RECRUITER reviewing this CV for a
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
{bpo_guard}

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
REAL CONTEXT (verified evidence only):
{real_context}

Never substitute one technology for another. Use only verified technologies, achievements and metrics.
Keep the skill inventory and per-role technology lists unchanged; reorder verified skills for relevance.
TONE: assert ("built/led"), never aspire ("looking to/eager to"). Every claim must survive an interview.
"""

    return f"""Adapt the following CV to better match the job description.

IMPORTANT RULES:
- NEVER change: company names, job titles, dates, education institutions, degree names, contact info, skill inventory or technology lists
- REWRITE: summary, experience descriptions, project descriptions to highlight relevant skills
- REORDER: skills list so matching skills come first
- LANGUAGE: Output the CV in the SAME language as the job description
- Start bullet points with action verbs
- Integrate the job's keywords naturally into real accomplishments — never as decoration
- ANTI-STUFFING: never reuse the same phrase across more than one bullet; do not prepend the job's headline term to every bullet; one truthful mention scores the same with an ATS as five. If a keyword can't be placed truthfully, leave it out.
- Preserve original job titles exactly
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
- Preserve the original job title and technology list exactly
- Rewrite description bullets using action verbs and relevant keywords
- Quantify achievements where the original implies measurable results
- Keep the same number of bullets (or fewer)
- Never substitute technologies or add skills that are not present in verified evidence
- TONE: assert what was done, never aspire

Experience entry:
{experience_json}

Return ONLY valid JSON with the same structure; only the description may change."""
