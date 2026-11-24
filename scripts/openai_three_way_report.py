"""Summarize a multi-model OpenAI CV simulation with the same offers and prompts.

Reads result.json / inspect.json / usage.jsonl / blind_ratings.json from the
experiment directory. It never calls an AI provider and never reads personal data.
"""
import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

MODEL_ORDER = ("gpt-6-luna", "gpt-6.1-terra", "gpt-6.2-sol")
PROMPT_ORDER = ("impacto", "reclutador", "natural", "enfoque", "breve")
RATES = {"gpt-6-luna": (0.10, 0.50), "gpt-6.1-terra": (1.0, 5.0), "gpt-6.2-sol": (2.0, 10.0)}
FIRST_PERSON = re.compile(
    r"\b(?:Diseñé|Lideré|Desarrollé|Implementé|Administré|Construí|Migré|Integré|Creé|"
    r"Rediseñé|Optimicé|Coordiné|Gestioné|Dirigí|Modernicé|Logré|Añadí|Automaticé|Documenté)\b"
)
THIRD_SUMMARY = re.compile(r"(?:^|\b)(?:Ha |Desarrolló|Lideró|Construyó|Implementó|Cuenta con|Posee)")


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


def mean(values):
    return round(statistics.mean(values), 1) if values else None


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines += ["| " + " | ".join(cell(item) for item in row) + " |" for row in rows]
    return "\n".join(lines)


def cost_of(usage_path):
    lines = []
    if usage_path.exists():
        try:
            lines = [json.loads(line) for line in usage_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except ValueError:
            lines = []
    total = 0.0
    for line in lines:
        model = line.get("model") or ""
        usage = line.get("usage") or {}
        if model not in RATES:
            continue
        inp = usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
        out = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
        pi, po = RATES[model]
        total += (inp * pi + out * po) / 1_000_000
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--title", default="Luna vs Terra vs Sol")
    args = parser.parse_args()
    exp = args.experiment.resolve()

    ratings = {}
    for block in read_json(exp / "blind_ratings.json", []) or []:
        mapping = block.get("mapping", {})
        for score in block.get("scores", []):
            label = mapping.get(score.get("id"), {})
            ratings[(block.get("job"), label.get("model"), label.get("prompt"))] = score

    records = []
    for path in sorted((exp / "runs").glob("*/result.json")):
        result = read_json(path, {})
        if not result:
            continue
        inspection = read_json(path.parent / "inspect.json", {}) or {}
        cv = inspection.get("adapted_cv", {}) or {}
        review = inspection.get("claim_review", {}) or {}
        quality = inspection.get("quality", {}) or {}
        model = result.get("model") or path.parent.name.split("__")[0]
        job = result.get("job", path.parent.name.split("__")[1])
        prompt = result.get("prompt", path.parent.name.split("__")[-1])
        complete = bool(result.get("success") and result.get("inspected") and quality.get("pdf_valid", result.get("pdf_valid")))
        score = ratings.get((job, model, prompt))
        records.append({
            "model": model, "job": job, "prompt": prompt,
            "expected_language": result.get("expected_language"),
            "seconds": result.get("seconds"),
            "complete": complete,
            "language_match": bool(result.get("language_label_matches", cv.get("detected_language") == result.get("expected_language"))),
            "refine_applied": bool(result.get("refine_applied")),
            "mixed_voice": mixed_voice(cv),
            "claim_status": review.get("status"),
            "unsupported": len(review.get("unsupported_claims", [])),
            "review_items": len(review.get("review_items", [])),
            "editorial_issues": len(quality.get("editorial_issues", [])),
            "served_tiers": result.get("served_tiers", []),
            "cost": cost_of(path.parent / "usage.jsonl"),
            "judge_total": score.get("total") if score else None,
            "judge_parts": score if score else None,
        })
    if not records:
        raise SystemExit("No result.json found")

    models = [m for m in MODEL_ORDER if any(r["model"] == m for r in records)]
    models += sorted({r["model"] for r in records} - set(models))
    jobs = sorted({r["job"] for r in records})
    prompts = [p for p in PROMPT_ORDER if any(r["prompt"] == p for r in records)]
    done = [r for r in records if r["complete"]]

    by_model = defaultdict(list)
    by_model_prompt = defaultdict(list)
    by_model_job = defaultdict(list)
    for record in done:
        by_model[record["model"]].append(record)
        by_model_prompt[(record["model"], record["prompt"])].append(record)
        by_model_job[(record["model"], record["job"])].append(record)

    job_titles, job_urls = {}, {}
    for path in sorted((exp / "jobs").glob("*.json")):
        data = read_json(path, {}) or {}
        job_titles[path.stem] = clean_title(data.get("title", "")) or path.stem
        job_urls[path.stem] = data.get("source_url", "")

    summary = {"experiment": str(exp), "cases": len(records), "completed": len(done), "models": {}}
    for model in models:
        rows = by_model[model]
        judged = [r for r in rows if r["judge_total"] is not None]
        parts = {}
        for part in ("language", "specificity", "relevance", "naturalness"):
            parts[part] = mean([r["judge_parts"][part] for r in judged if r["judge_parts"] and part in r["judge_parts"]])
        summary["models"][model] = {
            "cases": len([r for r in records if r["model"] == model]),
            "completed": len(rows),
            "language_match": sum(r["language_match"] for r in rows),
            "median_seconds": median([r["seconds"] for r in rows]),
            "mean_seconds": mean([r["seconds"] for r in rows]),
            "min_seconds": min([r["seconds"] for r in rows]) if rows else None,
            "max_seconds": max([r["seconds"] for r in rows]) if rows else None,
            "median_cost": round(statistics.median([r["cost"] for r in rows]), 5) if rows else None,
            "judge_mean": mean([r["judge_total"] for r in judged]),
            "judge_subscores": parts,
            "mixed_voice": sum(r["mixed_voice"] for r in rows),
            "spanish_cases": sum(1 for r in rows if r["expected_language"] == "es"),
            "unsupported": sum(r["unsupported"] for r in rows),
            "review_items": sum(r["review_items"] for r in rows),
            "editorial_issues": sum(r["editorial_issues"] for r in rows),
            "refine_applied": sum(r["refine_applied"] for r in rows),
            "served_tiers": dict(Counter(t for r in records if r["model"] == model for t in (r["served_tiers"] or []))),
            "by_prompt": {
                prompt: {"cases": len(by_model_prompt[(model, prompt)]),
                         "judge_mean": mean([r["judge_total"] for r in by_model_prompt[(model, prompt)] if r["judge_total"] is not None]),
                         "median_seconds": median([r["seconds"] for r in by_model_prompt[(model, prompt)]])}
                for prompt in prompts if by_model_prompt[(model, prompt)]
            },
            "by_job": {
                job: {"judge_mean": mean([r["judge_total"] for r in by_model_job[(model, job)] if r["judge_total"] is not None]),
                      "median_seconds": median([r["seconds"] for r in by_model_job[(model, job)]])}
                for job in jobs if by_model_job[(model, job)]
            },
        }

    lines = [
        f"# {args.title}",
        "",
        "Simulación de 10 ofertas reales de LinkedIn × 5 instrucciones de estilo × 3 modelos de OpenAI,",
        "con el mismo perfil sintético marcado «SIMULACION NO ENVIAR», la misma plantilla y el mismo flujo de dos pasadas.",
        "Ningún CV es una postulación ni representa a una persona real.",
        "",
        "## Diseño y evaluación",
        "",
        f"- {len(records)} condiciones; terminadas e inspeccionables: {len(done)}.",
        "- Todos los modelos usan service_tier=fast, la misma plantilla técnica y los mismos prompts (incluida la corrección de voz).",
        "- La nota ciega se calcula por oferta: los CV completados de los tres modelos y los cinco estilos se mezclan y se evalúan sin etiqueta de modelo, con rúbrica de 4 × 25 puntos.",
        "- La rúbrica mide consistencia de idioma, especificidad, pertinencia y naturalidad; no mide veracidad factual ni predice contratación.",
        "",
        "## Resultado global por modelo",
        "",
    ]
    rows = []
    for model in models:
        data = summary["models"][model]
        rows.append([model, f"{data['completed']} / {data['cases']}",
                     f"{data['language_match']} / {data['completed']}",
                     f"{data['median_seconds']} s",
                     ("USD " + format(data["median_cost"], ".5f")) if data["median_cost"] is not None else "—",
                     data["judge_mean"] if data["judge_mean"] is not None else "—",
                     f"{data['mixed_voice']} / {data['spanish_cases']}"])
    lines.append(table(["Modelo", "PDF / casos", "Idioma", "Mediana", "USD / CV", "Nota ciega", "Voz mixta"], rows))

    lines += ["", "## Comparación emparejada (misma oferta y prompt)", ""]
    labels = {"gpt-6-luna": "Luna", "gpt-6.1-terra": "Terra", "gpt-6.2-sol": "Sol"}
    totals = {(r["model"], r["job"], r["prompt"]): r["judge_total"] for r in done if r["judge_total"] is not None}
    pairs = [("gpt-6-luna", "gpt-6.1-terra"), ("gpt-6-luna", "gpt-6.2-sol"), ("gpt-6.1-terra", "gpt-6.2-sol")]
    rows = []
    for base, other in pairs:
        diffs = [totals[(other, job, prompt)] - totals[(base, job, prompt)] for job in jobs for prompt in prompts
                 if (other, job, prompt) in totals and (base, job, prompt) in totals]
        if not diffs:
            continue
        wins = sum(1 for d in diffs if d > 0)
        ties = sum(1 for d in diffs if d == 0)
        losses = sum(1 for d in diffs if d < 0)
        rows.append([f"{labels.get(other, other)} - {labels.get(base, base)}", f"{statistics.mean(diffs):+.2f}",
                     f"{statistics.median(diffs):+.1f}", f"{wins} / {ties} / {losses}",
                     f"{min(diffs):+d} / {max(diffs):+d}"])
    lines.append(table(["Diferencia", "Media", "Mediana", "Gana / Empata / Pierde", "Mín / Máx"], rows))

    lines += ["", "## Desglose de la nota ciega", ""]
    rows = []
    for model in models:
        data = summary["models"][model]
        parts = data["judge_subscores"]
        rows.append([model, parts["language"], parts["specificity"], parts["relevance"], parts["naturalness"], data["judge_mean"]])
    lines.append(table(["Modelo", "Lenguaje /25", "Especificidad /25", "Pertinencia /25", "Naturalidad /25", "Total /100"], rows))

    lines += ["", "## Nota ciega por modelo × instrucción", ""]
    rows = []
    for model in models:
        row = [model]
        for prompt in prompts:
            value = summary["models"][model]["by_prompt"].get(prompt, {}).get("judge_mean")
            row.append(value if value is not None else "—")
        rows.append(row)
    lines.append(table(["Modelo"] + list(prompts), rows))

    lines += ["", "## Mediana de tiempo por modelo × instrucción", ""]
    rows = []
    for model in models:
        row = [model]
        for prompt in prompts:
            value = summary["models"][model]["by_prompt"].get(prompt, {}).get("median_seconds")
            row.append(f"{value} s" if value is not None else "—")
        rows.append(row)
    lines.append(table(["Modelo"] + list(prompts), rows))

    lines += ["", "## Nota ciega por modelo × oferta", ""]
    rows = []
    for job in jobs:
        title = job_titles.get(job, job)
        if len(title) > 55:
            title = title[:52].rstrip() + "…"
        link = f"[{title}]({job_urls[job]})" if job_urls.get(job) else title
        row = [link]
        for model in models:
            value = summary["models"][model]["by_job"].get(job, {}).get("judge_mean")
            row.append(value if value is not None else "—")
        rows.append(row)
    labels = {"gpt-6-luna": "Luna", "gpt-6.1-terra": "Terra", "gpt-6.2-sol": "Sol"}
    lines.append(table(["Oferta"] + [labels.get(m, m) for m in models], rows))

    lines += ["", "## Revisión de afirmaciones y calidad editorial", ""]
    rows = []
    for model in models:
        data = summary["models"][model]
        rows.append([model, data["unsupported"], data["review_items"], data["editorial_issues"], data["refine_applied"]])
    lines.append(table(["Modelo", "No respaldadas", "A revisar", "Problemas editoriales", "Dos pasadas"], rows))

    lines += [
        "",
        "## Lectura",
        "",
        "- La comparación de nota es válida dentro de esta muestra: mismo perfil, mismas ofertas, mismos prompts y evaluación ciega por oferta.",
        "- Las diferencias de tiempo incluyen concurrencia, cuota y orden de ejecución; no son un benchmark aislado de latencia.",
        "- El costo es nominal, sin descuentos de caché, y se calcula con los tokens comunicados por el proveedor.",
        "- Una nota alta no demuestra que cada afirmación sea verdadera: los CV siguen siendo borradores de simulación pendientes de revisión.",
    ]
    out = args.out or (exp / "INFORME.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_out = args.json_out or (exp / "summary.json")
    json_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"markdown": str(out), "summary": str(json_out), "cases": len(records), "completed": len(done),
                      "models": {m: {"judge_mean": summary["models"][m]["judge_mean"],
                                     "median_seconds": summary["models"][m]["median_seconds"],
                                     "cost": summary["models"][m]["median_cost"]} for m in models}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
