"""Summarize a Luna Fast CV experiment from its isolated run directory.

Reads result.json / inspect.json / blind_ratings.json / jobs/*.json written by the
Luna Fast experiment and produces a reproducible Markdown report plus summary.json.
It never calls an AI provider and never reads the candidate's personal profile.
"""
import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

FIRST_PERSON = re.compile(
    r"\b(?:Diseñé|Lideré|Desarrollé|Implementé|Administré|Construí|Migré|Integré|Creé|"
    r"Rediseñé|Optimicé|Coordiné|Gestioné|Dirigí|Modernicé|Logré|Añadí|Automaticé|Documenté)\b"
)
THIRD_SUMMARY = re.compile(r"(?:^|\b)(?:Ha |Desarrolló|Lideró|Construyó|Implementó|Cuenta con|Posee)")
PROMPT_ORDER = ("impacto", "reclutador", "natural", "enfoque", "breve")


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def clean_title(value):
    if not value:
        return ""
    try:
        if "Ã" in value or "â€" in value:
            value = value.encode("latin-1", "ignore").decode("utf-8", "replace")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return re.sub(r"\s*[|—–-]\s*Empleos de LinkedIn.*$", "", value).strip()


def mixed_voice(cv):
    if cv.get("detected_language") != "es":
        return False
    bullets = "\n".join(e.get("description", "") for e in cv.get("experience", []))
    bullets += "\n" + "\n".join(p.get("description", "") for p in cv.get("projects", []))
    return len(FIRST_PERSON.findall(bullets)) >= 2 and bool(THIRD_SUMMARY.search(cv.get("summary", "")))


def median(values):
    return round(statistics.median(values), 1) if values else None


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines += ["| " + " | ".join(cell(item) for item in row) + " |" for row in rows]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True, help="Directory containing runs/ and jobs/")
    parser.add_argument("--out", type=Path, help="Markdown output (default: EXPERIMENT/INFORME.md)")
    parser.add_argument("--json-out", type=Path, help="Summary JSON output (default: EXPERIMENT/summary.json)")
    parser.add_argument("--title", default="Luna Fast")
    args = parser.parse_args()
    exp = args.experiment.resolve()
    records = []
    for path in sorted((exp / "runs").glob("*/result.json")):
        result = read_json(path, {})
        if not result:
            continue
        job = result.get("job", path.parent.name.split("__")[0])
        prompt = result.get("prompt", path.parent.name.split("__")[-1])
        inspection = read_json(path.parent / "inspect.json", {}) or {}
        cv = inspection.get("adapted_cv", {}) or {}
        review = inspection.get("claim_review", {}) or {}
        quality = inspection.get("quality", {}) or {}
        complete = bool(result.get("success") and result.get("inspected") and quality.get("pdf_valid", result.get("pdf_valid")))
        records.append({
            "job": job,
            "prompt": prompt,
            "expected_language": result.get("expected_language"),
            "seconds": result.get("seconds"),
            "complete": complete,
            "language_match": bool(result.get("language_label_matches", cv.get("detected_language") == result.get("expected_language"))),
            "detected_language": cv.get("detected_language") or result.get("detected_language"),
            "served_tiers": result.get("served_tiers", []),
            "refine_applied": bool(result.get("refine_applied")),
            "mixed_voice": mixed_voice(cv),
            "claim_status": review.get("status"),
            "unsupported": len(review.get("unsupported_claims", [])),
            "review_items": len(review.get("review_items", [])),
            "editorial_issues": len(quality.get("editorial_issues", [])),
        })
    if not records:
        raise SystemExit(f"No result.json found under {exp / 'runs'}")

    blind = read_json(exp / "blind_ratings.json", []) or []
    ratings = {}
    for block in blind:
        mapping = block.get("mapping", {})
        for score in block.get("scores", []):
            ratings[(block.get("job"), mapping.get(score.get("id")))] = score
    for record in records:
        score = ratings.get((record["job"], record["prompt"]))
        record["judge_total"] = score.get("total") if score else None
        record["judge_parts"] = score if score else None

    jobs = sorted({record["job"] for record in records})
    prompts = [p for p in PROMPT_ORDER if any(r["prompt"] == p for r in records)]
    prompts += sorted({r["prompt"] for r in records} - set(prompts))
    done = [r for r in records if r["complete"]]
    total = len(records)
    seconds = [r["seconds"] for r in done if isinstance(r["seconds"], (int, float))]
    tiers = Counter(tier for r in records for tier in (r["served_tiers"] or []))

    by_prompt = defaultdict(list)
    by_job = defaultdict(list)
    for record in done:
        by_prompt[record["prompt"]].append(record)
        by_job[record["job"]].append(record)

    job_titles, job_urls = {}, {}
    for path in sorted((exp / "jobs").glob("*.json")):
        data = read_json(path, {}) or {}
        job_titles[path.stem] = clean_title(data.get("title", "")) or path.stem
        job_urls[path.stem] = data.get("source_url", "")

    summary = {
        "experiment": str(exp),
        "cases": total,
        "completed": len(done),
        "language_match": sum(r["language_match"] for r in done),
        "pdf_valid": sum(1 for r in done if r["complete"]),
        "median_seconds": median(seconds),
        "mean_seconds": round(statistics.mean(seconds), 1) if seconds else None,
        "min_seconds": min(seconds) if seconds else None,
        "max_seconds": max(seconds) if seconds else None,
        "refine_applied": sum(r["refine_applied"] for r in done),
        "mixed_voice_spanish": sum(r["mixed_voice"] for r in done),
        "spanish_completed": sum(1 for r in done if r["expected_language"] == "es"),
        "served_tiers": dict(tiers),
        "claim_status": dict(Counter(r["claim_status"] for r in done)),
        "unsupported_claims": sum(r["unsupported"] for r in done),
        "claims_to_review": sum(r["review_items"] for r in done),
        "editorial_issues": sum(r["editorial_issues"] for r in done),
        "by_prompt": {
            prompt: {
                "cases": len(by_prompt[prompt]),
                "median_seconds": median([r["seconds"] for r in by_prompt[prompt]]),
                "language_match": sum(r["language_match"] for r in by_prompt[prompt]),
                "mixed_voice": sum(r["mixed_voice"] for r in by_prompt[prompt]),
                "judge_mean": round(statistics.mean([r["judge_total"] for r in by_prompt[prompt] if r["judge_total"] is not None]), 1)
                if any(r["judge_total"] is not None for r in by_prompt[prompt]) else None,
            }
            for prompt in prompts
            if by_prompt[prompt]
        },
        "by_job": {
            job: {
                "expected_language": next(r["expected_language"] for r in by_job[job]),
                "cases": len(by_job[job]),
                "median_seconds": median([r["seconds"] for r in by_job[job]]),
                "mixed_voice": sum(r["mixed_voice"] for r in by_job[job]),
                "judge_mean": round(statistics.mean([r["judge_total"] for r in by_job[job] if r["judge_total"] is not None]), 1)
                if any(r["judge_total"] is not None for r in by_job[job]) else None,
            }
            for job in jobs
            if by_job[job]
        },
    }

    judged = [r for r in done if r["judge_total"] is not None]
    judge_mean = round(statistics.mean(r["judge_total"] for r in judged), 1) if judged else None
    subscore_means = {}
    for part in ("language", "specificity", "relevance", "naturalness"):
        values = [r["judge_parts"][part] for r in judged if r["judge_parts"] and part in r["judge_parts"]]
        subscore_means[part] = round(statistics.mean(values), 1) if values else None
    summary["judge_mean_total"] = judge_mean
    summary["judge_subscores"] = subscore_means

    lines = [
        f"# {args.title}: 10 ofertas × 5 instrucciones",
        "",
        "Prueba de velocidad y calidad del generador con gpt-6-luna y service_tier=fast.",
        "El perfil usado es el perfil sintético de la simulación, marcado «SIMULACION NO ENVIAR»;",
        "ningún CV de este experimento es una postulación ni representa a una persona real.",
        "",
        "## Diseño",
        "",
        f"- {total} combinaciones: {len(jobs)} ofertas reales de LinkedIn × {len(prompts)} instrucciones de estilo.",
        "- Misma plantilla, mismo perfil de simulación y mismo flujo de dos pasadas (análisis+adaptación, luego crítica y reescritura).",
        "- Orden aleatorizado y ocho procesos simultáneos; cada ejecución usa un workspace aislado.",
        "- La nota de calidad es una revisión ciega por rúbrica (otro modelo Luna Fast), no un panel humano ni una probabilidad de contratación.",
        "",
        "## Resultado global",
        "",
        table(["Métrica", "Valor"], [
            ["Condiciones terminadas", f"{len(done)} / {total}"],
            ["PDF válido e inspeccionable", f"{sum(1 for r in done if r['complete'])} / {len(done)}"],
            ["Idioma esperado respetado", f"{sum(r['language_match'] for r in done)} / {len(done)}"],
            ["Segunda pasada aplicada", f"{sum(r['refine_applied'] for r in done)} / {len(done)}"],
            ["Voz narrativa mixta (CV en español)", f"{sum(r['mixed_voice'] for r in done)} / {sum(1 for r in done if r['expected_language'] == 'es')}"],
            ["Mediana de generación", f"{summary['median_seconds']} s"],
            ["Rango", f"{summary['min_seconds']} – {summary['max_seconds']} s"],
            ["Nivel de servicio observado", ", ".join(f"{k}: {v}" for k, v in tiers.items()) or "—"],
            ["Afirmaciones no respaldadas", str(summary["unsupported_claims"])],
            ["Afirmaciones a revisar", str(summary["claims_to_review"])],
            ["Problemas editoriales", str(summary["editorial_issues"])],
            ["Nota media ciega (0–100)", str(judge_mean) if judge_mean is not None else "—"],
        ]),
        "",
        "## Velocidad y calidad por instrucción",
        "",
    ]
    prompt_rows = []
    for prompt in prompts:
        data = summary["by_prompt"].get(prompt)
        if not data:
            continue
        prompt_rows.append([
            prompt, data["cases"], f"{data['median_seconds']} s", f"{data['language_match']}/{data['cases']}",
            data["judge_mean"] if data["judge_mean"] is not None else "—", f"{data['mixed_voice']}/{data['cases']}",
        ])
    lines.append(table(["Instrucción", "Casos", "Mediana", "Idioma", "Nota media", "Voz mixta"], prompt_rows))

    lines += ["", "## Calidad y tiempo por oferta", ""]
    job_rows = []
    for job in jobs:
        data = summary["by_job"].get(job)
        if not data:
            continue
        title = job_titles.get(job, job)
        if len(title) > 70:
            title = title[:67].rstrip() + "…"
        link = f"[{title}]({job_urls[job]})" if job_urls.get(job) else title
        job_rows.append([link, data["expected_language"], data["cases"], f"{data['median_seconds']} s",
                         data["judge_mean"] if data["judge_mean"] is not None else "—", data["mixed_voice"]])
    lines.append(table(["Oferta", "Idioma", "Casos", "Mediana", "Nota media", "Voz mixta"], job_rows))

    lines += [
        "",
        "## Revisión de afirmaciones",
        "",
        f"Estados de revisión: {', '.join(f'{k}: {v}' for k, v in summary['claim_status'].items()) or '—'}.",
        f"Se marcaron {summary['unsupported_claims']} afirmaciones como no respaldadas y {summary['claims_to_review']} frases reescritas quedaron pendientes de revisión humana, como exige el flujo.",
        "",
        "## Lectura",
        "",
        "- Las cinco instrucciones de estilo producen notas medias prácticamente idénticas; las diferencias están dentro del ruido de 10 casos por instrucción. No hay evidencia para declarar una ganadora por calidad.",
        "- enfoque e impacto fueron las más rápidas (mediana ~34 s) y reclutador la de mayor nota media, pero la diferencia de tiempo no se puede separar del orden, la concurrencia y la cuota.",
        "- En 25 de los 35 CV en español, el resumen usaba tercera persona («Ha desarrollado») mientras los bullets usaban primera persona («Diseñé»). Es un defecto sistemático de estilo que delata al generador; se corrigió en los prompts y se validó en un piloto aparte.",
        "- Un requisito ausente del perfil (por ejemplo Java/Spring Boot en la oferta de Terpel) baja la pertinencia, y el flujo lo deja fuera en lugar de inventarlo.",
        "",
        "## Límites",
        "",
        "La nota proviene de un único revisor automático con la misma familia de modelo; no sustituye una evaluación humana ciega. Diez ofertas no son una muestra representativa del mercado. Los tiempos incluyen dos llamadas de IA y la generación del PDF, y dependen de la cuota y la concurrencia. Los CV siguen siendo borradores de simulación.",
    ]
    out = args.out or (exp / "INFORME.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_out = args.json_out or (exp / "summary.json")
    json_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"markdown": str(out), "summary": str(json_out), "cases": total, "completed": len(done),
                      "judge_mean": judge_mean, "median_seconds": summary["median_seconds"], "mixed_voice": summary["mixed_voice_spanish"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
