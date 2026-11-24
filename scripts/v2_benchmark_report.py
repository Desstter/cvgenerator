"""Comprehensive report for the v2 three-model CV benchmark.

Reads result.json / inspect.json / usage.jsonl / blind_ratings_<suffix>.json and
writes a Markdown report, summary.json, summary.csv and charts under docs/assets/v2.
It never calls an AI provider.
"""
import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

MODEL_ORDER = ("gpt-6-luna", "gpt-6.1-terra", "gpt-6.2-sol")
PROMPT_ORDER = ("impacto", "reclutador", "natural", "enfoque", "breve", "defensa")
MODEL_LABEL = {"gpt-6-luna": "Luna", "gpt-6.1-terra": "Terra", "gpt-6.2-sol": "Sol"}
RATES = {"gpt-6-luna": (0.10, 0.50), "gpt-6.1-terra": (1.0, 5.0), "gpt-6.2-sol": (2.0, 10.0)}
CRITERIA = ("language", "specificity", "relevance", "naturalness", "impact", "credibility")
CRITERIA_LABEL = {"language": "Lenguaje", "specificity": "Especificidad", "relevance": "Pertinencia",
                  "naturalness": "Naturalidad", "impact": "Impacto", "credibility": "Credibilidad"}
BULLET = re.compile(r"(?m)^\s*[•\-]\s+(.+)$")
FORBIDDEN = re.compile(r"^(responsable de|ayud[eé] a|trabaj[eé] (en|con)|particip[eé] en|encargad[oa] de|"
                       r"responsible for|helped|worked (on|with)|participated in|assisted|involved in|in charge of)", re.I)
BUZZ = ("apasionad", "proactiv", "orientado a resultados", "sinergia", "innovador", "disruptiv", "vanguardia",
        "results-driven", "passionate", "proactive", "synergy", "cutting-edge", "innovative", "self-starter",
        "dynamic", "world-class", "best-in-class", "de clase mundial", "pensamiento disruptivo")
FIRST_PERSON = re.compile(
    r"\b(?:Diseñé|Lideré|Desarrollé|Implementé|Administré|Construí|Migré|Integré|Creé|Rediseñé|Optimicé|"
    r"Coordiné|Gestioné|Dirigí|Modernicé|Logré|Añadí|Automaticé|Documenté)\b")
THIRD_SUMMARY = re.compile(r"(?:^|\b)(?:Ha |Desarrolló|Lideró|Construyó|Implementó|Cuenta con|Posee)")


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def mean(values):
    return round(statistics.mean(values), 2) if values else None


def median(values):
    return round(statistics.median(values), 1) if values else None


def p90(values):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(math.ceil(0.9 * len(ordered))) - 1)
    return round(ordered[index], 1)


def ratio(part, total):
    return round(100 * part / total, 1) if total else None


def clean_title(value):
    if not value:
        return ""
    try:
        if "Ã" in value or "â€" in value:
            value = value.encode("latin-1", "ignore").decode("utf-8", "replace")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return re.sub(r"\s*[|—–-]\s*Empleos de LinkedIn.*$", "", value).strip()


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
        usage = line.get("usage") or {}
        model = line.get("model") or ""
        if model not in RATES:
            continue
        inp = usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
        out = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
        pi, po = RATES[model]
        total += (inp * pi + out * po) / 1_000_000
    return total


def mixed_voice(cv):
    if cv.get("detected_language") != "es":
        return False
    bullets = "\n".join(e.get("description", "") for e in cv.get("experience", []))
    bullets += "\n" + "\n".join(p.get("description", "") for p in cv.get("projects", []))
    return len(FIRST_PERSON.findall(bullets)) >= 2 and bool(THIRD_SUMMARY.search(cv.get("summary", "")))


def page_count(pdf_path):
    try:
        import pymupdf
        return pymupdf.open(pdf_path).page_count
    except Exception:
        return None


def protected_ok(source, adapted):
    try:
        if source.get("contact") != adapted.get("contact"):
            return False
        se, ae = source.get("experience", []), adapted.get("experience", [])
        if [e.get("company") for e in se] != [e.get("company") for e in ae]:
            return False
        if [e.get("title") for e in se] != [e.get("title") for e in ae]:
            return False
        if [e.get("dates") for e in se] != [e.get("dates") for e in ae]:
            return False
        if source.get("education") != adapted.get("education"):
            return False
        return True
    except (AttributeError, TypeError):
        return False


def cv_metrics(cv, source, quality, review, pdf_path):
    text = cv.get("summary", "")
    text += "\n" + "\n".join(e.get("description", "") for e in cv.get("experience", []))
    text += "\n" + "\n".join(p.get("description", "") for p in cv.get("projects", []))
    bullets = [b.strip() for b in BULLET.findall(text) if b.strip()]
    if not bullets:
        bullets = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    words = text.split()
    bullet_words = [len(re.findall(r"[\wÁÉÍÓÚÜÑáéíóúüñ+#.]+", b)) for b in bullets]
    tokens = re.findall(r"[a-záéíóúñü0-9]+", text.lower())
    ngrams = [tuple(tokens[i:i + 4]) for i in range(max(0, len(tokens) - 3))]
    repeated = (len(ngrams) - len(set(ngrams))) / len(ngrams) if ngrams else 0.0
    coverage = (quality.get("keyword_coverage") or {})
    return {
        "words": len(words),
        "bullets": len(bullets),
        "avg_words_bullet": round(statistics.mean(bullet_words), 1) if bullet_words else None,
        "long_bullet_ratio": ratio(sum(1 for n in bullet_words if n >= 35), len(bullet_words)),
        "quantified_ratio": ratio(sum(1 for b in bullets if re.search(r"\d|%|\bx\b", b)), len(bullets)),
        "forbidden_openers": sum(1 for b in bullets if FORBIDDEN.match(b)),
        "buzzwords": sum(len(re.findall(re.escape(w), text, re.I)) for w in BUZZ),
        "buzz_per_100": round(100 * sum(len(re.findall(re.escape(w), text, re.I)) for w in BUZZ) / max(1, len(words)), 2),
        "repeated_4gram_ratio": round(100 * repeated, 2),
        "coverage_overall": coverage.get("overall_score"),
        "coverage_required": coverage.get("required_score"),
        "coverage_preferred": coverage.get("preferred_score"),
        "pages": page_count(pdf_path),
        "protected_ok": protected_ok(source, cv),
        "unsupported": len(review.get("unsupported_claims", [])),
        "review_items": len(review.get("review_items", [])),
        "claim_status": review.get("status"),
    }


def load_ratings(exp, suffix):
    ratings, duplicates = {}, []
    for block in read_json(exp / f"blind_ratings_{suffix}.json", []) or []:
        mapping = block.get("mapping", {})
        by_id = {score.get("id"): score for score in block.get("scores", [])}
        for cid, label in mapping.items():
            if cid in by_id and "duplicate_of" not in label:
                ratings[(block.get("job"), label.get("model"), label.get("prompt"))] = by_id[cid]
        for cid, label in mapping.items():
            if "duplicate_of" in label and cid in by_id and label["duplicate_of"] in by_id:
                duplicates.append({"job": block.get("job"), "model": label.get("model"), "prompt": label.get("prompt"),
                                   "delta": by_id[cid]["total"] - by_id[label["duplicate_of"]]["total"]})
    return ratings, duplicates


def pearson(xs, ys):
    if len(xs) < 2:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return round(num / den, 3) if den else None


def spearman(xs, ys):
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        result = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                result[order[k]] = rank
            i = j + 1
        return result
    return pearson(ranks(xs), ranks(ys))


def make_charts(summary, models, jobs, job_titles, common, charts_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return {}
    charts_dir.mkdir(parents=True, exist_ok=True)
    labels = [MODEL_LABEL.get(m, m) for m in models]
    colors = ["#4C78A8", "#F58518", "#54A24B"][:len(models)]
    paths = {}
    values = {
        "score": [summary["models"][m]["judge_score_100"] or 0 for m in models],
        "seconds": [summary["models"][m]["median_seconds"] or 0 for m in models],
        "cost": [1000 * (summary["models"][m]["median_cost"] or 0) for m in models],
    }
    titles = {"score": "Nota juez Sol /100", "seconds": "Mediana de generacion (s)", "cost": "Miles de USD por CV"}
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    for ax, key in zip(axes, ("score", "seconds", "cost")):
        bars = ax.bar(labels, values[key], color=colors)
        ax.set_title(titles[key])
        for bar, value in zip(bars, values[key]):
            label = f"{value:.1f}" if key != "cost" else f"{value:.2f}"
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), label, ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    target = charts_dir / "quality_speed_cost.png"
    fig.savefig(target, dpi=160)
    plt.close(fig)
    paths["summary"] = target

    data = [[(summary["models"][m]["by_job"].get(job, {}).get("judge_total") or 0) / 1.2 for m in models] for job in jobs]
    fig, ax = plt.subplots(figsize=(5.5, max(6, 0.38 * len(jobs))))
    image = ax.imshow(data, cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_yticks(range(len(jobs)))
    ax.set_yticklabels([job_titles.get(job, job)[:28] for job in jobs], fontsize=7)
    for i in range(len(jobs)):
        for k in range(len(models)):
            ax.text(k, i, f"{data[i][k]:.0f}", ha="center", va="center", fontsize=7, color="black")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    target = charts_dir / "quality_by_offer.png"
    fig.savefig(target, dpi=160)
    plt.close(fig)
    paths["heatmap"] = target

    criteria = list(CRITERIA)
    angles = [2 * 3.141592653589793 * i / len(criteria) for i in range(len(criteria))]
    angles += angles[:1]
    fig = plt.figure(figsize=(5.2, 5.2))
    ax = fig.add_subplot(111, polar=True)
    for model, color in zip(models, colors):
        parts = summary["models"][model]["judge_subscores"]
        values = [parts.get(c) or 0 for c in criteria]
        values += values[:1]
        ax.plot(angles, values, color=color, linewidth=2, label=MODEL_LABEL.get(model, model))
        ax.fill(angles, values, color=color, alpha=0.10)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([CRITERIA_LABEL[c] for c in criteria], fontsize=8)
    ax.set_ylim(0, 20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1), fontsize=8)
    ax.set_title("Perfil de criterios (juez Sol)", fontsize=10)
    fig.tight_layout()
    target = charts_dir / "criteria_radar.png"
    fig.savefig(target, dpi=160)
    plt.close(fig)
    paths["radar"] = target

    prompts_present = [p for p in PROMPT_ORDER if any(p in summary["models"][m]["by_prompt"] for m in models)]
    if prompts_present:
        prompt_data = [[(summary["models"][m]["by_prompt"].get(p, {}).get("judge_total") or 0) / 1.2 for p in prompts_present] for m in models]
        fig, ax = plt.subplots(figsize=(7, 3.2))
        image = ax.imshow(prompt_data, cmap="YlGnBu", aspect="auto")
        ax.set_xticks(range(len(prompts_present)))
        ax.set_xticklabels(prompts_present, fontsize=8)
        ax.set_yticks(range(len(models)))
        ax.set_yticklabels(labels, fontsize=8)
        for i in range(len(models)):
            for k in range(len(prompts_present)):
                ax.text(k, i, f"{prompt_data[i][k]:.0f}", ha="center", va="center", fontsize=8)
        fig.colorbar(image, ax=ax, fraction=0.03, pad=0.02)
        ax.set_title("Nota por instrucción (juez Sol /100)", fontsize=10)
        fig.tight_layout()
        target = charts_dir / "prompt_heatmap.png"
        fig.savefig(target, dpi=160)
        plt.close(fig)
        paths["prompts"] = target

    if common:
        fig, ax = plt.subplots(figsize=(4.4, 4.4))
        ax.scatter([r["judge_total"] for r in common], [r["judge2_total"] for r in common], s=12, alpha=0.5, color="#54A24B")
        ax.plot([0, 120], [0, 120], "--", color="#999999", linewidth=1)
        ax.set_xlabel("Juez Sol /120")
        ax.set_ylabel("Juez Luna /120")
        ax.set_title("Acuerdo entre jueces")
        fig.tight_layout()
        target = charts_dir / "judge_agreement.png"
        fig.savefig(target, dpi=160)
        plt.close(fig)
        paths["agreement"] = target
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--charts", type=Path, default=Path("docs/assets/v2"))
    parser.add_argument("--title", default="Benchmark v2: Luna vs Terra vs Sol")
    args = parser.parse_args()
    exp = args.experiment.resolve()
    primary, dup_primary = load_ratings(exp, "sol")
    secondary, _ = load_ratings(exp, "luna")

    records = []
    for path in sorted((exp / "runs").glob("*/result.json")):
        result = read_json(path, {})
        if not result:
            continue
        inspection = read_json(path.parent / "inspect.json", {}) or {}
        cv = inspection.get("adapted_cv", {}) or {}
        source = inspection.get("source_cv", {}) or {}
        quality = inspection.get("quality", {}) or {}
        review = inspection.get("claim_review", {}) or {}
        model = result.get("model") or path.parent.name.split("__")[0]
        job = result.get("job", path.parent.name.split("__")[1])
        prompt = result.get("prompt", path.parent.name.split("__")[-1])
        complete = bool(result.get("success") and result.get("inspected") and quality.get("pdf_valid", result.get("pdf_valid")))
        metrics = cv_metrics(cv, source, quality, review, inspection.get("pdf_path", ""))
        score = primary.get((job, model, prompt))
        second = secondary.get((job, model, prompt))
        records.append({
            "model": model, "job": job, "prompt": prompt,
            "expected_language": result.get("expected_language"),
            "seconds": result.get("seconds"),
            "complete": complete,
            "language_match": bool(result.get("language_label_matches", cv.get("detected_language") == result.get("expected_language"))),
            "refine_applied": bool(result.get("refine_applied")),
            "mixed_voice": mixed_voice(cv),
            "served_tiers": result.get("served_tiers", []),
            "cost": cost_of(path.parent / "usage.jsonl"),
            "judge_total": score.get("total") if score else None,
            "judge_parts": score if score else None,
            "judge2_total": second.get("total") if second else None,
            **metrics,
        })
    if not records:
        raise SystemExit("No result.json found")
    done = [r for r in records if r["complete"]]

    models = [m for m in MODEL_ORDER if any(r["model"] == m for r in records)]
    jobs = sorted({r["job"] for r in records})
    prompts = [p for p in PROMPT_ORDER if any(r["prompt"] == p for r in records)]

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

    dup_by_model = defaultdict(list)
    for item in dup_primary:
        dup_by_model[item["model"]].append(abs(item["delta"]))

    summary = {"experiment": str(exp), "cases": len(records), "completed": len(done), "models": {},
               "judge_agreement": None, "duplicates": {}}
    for model in models:
        rows = by_model[model]
        judged = [r for r in rows if r["judge_total"] is not None]
        judged2 = [r for r in rows if r["judge2_total"] is not None]
        parts = {c: mean([r["judge_parts"][c] for r in judged if r["judge_parts"] and c in r["judge_parts"]]) for c in CRITERIA}
        summary["models"][model] = {
            "cases": len([r for r in records if r["model"] == model]),
            "completed": len(rows),
            "language_match": sum(r["language_match"] for r in rows),
            "one_page": sum(1 for r in rows if r["pages"] == 1),
            "median_seconds": median([r["seconds"] for r in rows]),
            "p90_seconds": p90([r["seconds"] for r in rows]),
            "median_cost": round(statistics.median([r["cost"] for r in rows]), 5) if rows else None,
            "judge_total": mean([r["judge_total"] for r in judged]),
            "judge_score_100": round(mean([r["judge_total"] for r in judged]) / 1.2, 1) if judged else None,
            "judge_subscores": parts,
            "judge2_total": mean([r["judge2_total"] for r in judged2]),
            "judge2_score_100": round(mean([r["judge2_total"] for r in judged2]) / 1.2, 1) if judged2 else None,
            "duplicate_abs_delta": round(statistics.mean(dup_by_model[model]), 1) if dup_by_model[model] else None,
            "words": mean([r["words"] for r in rows]),
            "bullets": mean([r["bullets"] for r in rows]),
            "avg_words_bullet": mean([r["avg_words_bullet"] for r in rows if r["avg_words_bullet"] is not None]),
            "long_bullet_ratio": mean([r["long_bullet_ratio"] for r in rows if r["long_bullet_ratio"] is not None]),
            "quantified_ratio": mean([r["quantified_ratio"] for r in rows if r["quantified_ratio"] is not None]),
            "forbidden_openers": sum(r["forbidden_openers"] for r in rows),
            "buzz_per_100": mean([r["buzz_per_100"] for r in rows]),
            "repeated_4gram_ratio": mean([r["repeated_4gram_ratio"] for r in rows]),
            "coverage_overall": mean([r["coverage_overall"] for r in rows if r["coverage_overall"] is not None]),
            "protected_ok_pct": ratio(sum(1 for r in rows if r["protected_ok"]), len(rows)),
            "unsupported": sum(r["unsupported"] for r in rows),
            "review_items": sum(r["review_items"] for r in rows),
            "mixed_voice": sum(r["mixed_voice"] for r in rows),
            "spanish_cases": sum(1 for r in rows if r["expected_language"] == "es"),
            "refine_applied": sum(r["refine_applied"] for r in rows),
            "served_tiers": dict(Counter(t for r in records if r["model"] == model for t in (r["served_tiers"] or []))),
            "by_language": {lang: {"cases": len([r for r in rows if r["expected_language"] == lang]),
                                    "judge_total": mean([r["judge_total"] for r in rows if r["expected_language"] == lang and r["judge_total"] is not None]),
                                    "median_seconds": median([r["seconds"] for r in rows if r["expected_language"] == lang])}
                            for lang in ("es", "en") if any(r["expected_language"] == lang for r in rows)},
            "by_prompt": {p: {"cases": len(by_model_prompt[(model, p)]),
                              "judge_total": mean([r["judge_total"] for r in by_model_prompt[(model, p)] if r["judge_total"] is not None]),
                              "median_seconds": median([r["seconds"] for r in by_model_prompt[(model, p)]])}
                          for p in prompts if by_model_prompt[(model, p)]},
            "by_job": {j: {"judge_total": mean([r["judge_total"] for r in by_model_job[(model, j)] if r["judge_total"] is not None]),
                           "median_seconds": median([r["seconds"] for r in by_model_job[(model, j)]])}
                       for j in jobs if by_model_job[(model, j)]},
        }

    common = [r for r in done if r["judge_total"] is not None and r["judge2_total"] is not None]
    agreement = {
        "n": len(common),
        "pearson": pearson([r["judge_total"] for r in common], [r["judge2_total"] for r in common]),
        "spearman": spearman([r["judge_total"] for r in common], [r["judge2_total"] for r in common]),
        "mean_abs_diff": round(statistics.mean(abs(r["judge_total"] - r["judge2_total"]) for r in common), 2) if common else None,
        "model_means_sol_judge": {m: mean([r["judge_total"] for r in common if r["model"] == m]) for m in models},
        "model_means_luna_judge": {m: mean([r["judge2_total"] for r in common if r["model"] == m]) for m in models},
    }
    summary["judge_agreement"] = agreement
    summary["duplicates"] = {m: {"n": len(dup_by_model[m]), "mean_abs_delta": round(statistics.mean(dup_by_model[m]), 1)}
                             if dup_by_model[m] else {"n": 0, "mean_abs_delta": None} for m in models}

    def paired(base, other, field="judge_total"):
        diffs = []
        for row in done:
            if row["model"] != other or row[field] is None:
                continue
            baseline = next((b for b in done if b["model"] == base and b["job"] == row["job"] and b["prompt"] == row["prompt"]), None)
            if baseline is None or baseline[field] is None:
                continue
            diffs.append(row[field] - baseline[field])
        if not diffs:
            return None
        return {"mean": round(statistics.mean(diffs), 2), "median": round(statistics.median(diffs), 1),
                "wins": sum(1 for d in diffs if d > 0), "ties": sum(1 for d in diffs if d == 0),
                "losses": sum(1 for d in diffs if d < 0), "n": len(diffs),
                "min": min(diffs), "max": max(diffs)}

    pairs = [("gpt-6-luna", "gpt-6.1-terra"), ("gpt-6-luna", "gpt-6.2-sol"), ("gpt-6.1-terra", "gpt-6.2-sol")]
    summary["paired"] = {f"{b} - {a}": paired(a, b) for a, b in pairs}
    chart_paths = make_charts(summary, models, jobs, job_titles, common, args.charts)

    lines = [
        f"# {args.title}",
        "",
        "20 ofertas reales de LinkedIn × 6 instrucciones de estilo × 3 modelos de OpenAI, con el mismo perfil",
        "sintético marcado «SIMULACION NO ENVIAR», la misma plantilla y el mismo flujo de dos pasadas.",
        "Ningún CV es una postulación ni representa a una persona real.",
        "",
        "## Diseño",
        "",
        f"- {len(records)} condiciones; terminadas e inspeccionables: {len(done)}.",
        "- Modelos: Luna, Terra y Sol; todos con service_tier=fast.",
        "- Ofertas: 10 ya usadas en la prueba anterior + 10 nuevas, en español e inglés.",
        "- Instrucciones: impacto, reclutador, natural, enfoque, breve y defensa (defendible en entrevista).",
        "- Evaluación principal: Sol como juez ciego; evaluación secundaria: Luna como segundo juez ciego para medir acuerdo.",
        "- Rúbrica: 6 criterios × 20 puntos = 120; se normaliza a 100. Además se mide una CV duplicada por oferta para estimar consistencia del juez.",
        "- Métricas automáticas: una página, palabras, bullets, bullets cuantificados, aperturas prohibidas, buzzwords, repetición de 4-gramos, cobertura de keywords, campos protegidos y revisión de afirmaciones.",
        "",
        "## Resultado global por modelo",
        "",
    ]
    rows = []
    for model in models:
        data = summary["models"][model]
        cost = data["median_cost"]
        rows.append([MODEL_LABEL.get(model, model), f"{data['completed']} / {data['cases']}",
                     f"{data['language_match']} / {data['completed']}",
                     f"{data['one_page']} / {data['completed']}",
                     f"{data['median_seconds']} s", f"{data['p90_seconds']} s",
                     format(cost, ".5f") if cost is not None else "—",
                     format(100 * cost, ".2f") if cost is not None else "—",
                     data["judge_score_100"] if data["judge_score_100"] is not None else "—",
                     data["judge2_score_100"] if data["judge2_score_100"] is not None else "—"])
    lines.append(table(["Modelo", "PDF", "Idioma", "1 página", "p50", "p90", "USD / CV", "USD / 100", "Sol /100", "Luna /100"], rows))

    lines += ["", "## Resultado por idioma de la oferta", ""]
    rows = []
    for model in models:
        data = summary["models"][model]["by_language"]
        es = data.get("es", {})
        en = data.get("en", {})
        rows.append([MODEL_LABEL.get(model, model),
                     f"{es.get('cases', 0)} / {es.get('judge_total', '—')}",
                     f"{en.get('cases', 0)} / {en.get('judge_total', '—')}",
                     f"{es.get('median_seconds', '—')} s", f"{en.get('median_seconds', '—')} s"])
    lines.append(table(["Modelo", "ES: casos / nota /120", "EN: casos / nota /120", "ES p50", "EN p50"], rows))

    lines += ["", "## Criterios del juez Sol (0–20)", ""]
    rows = []
    for model in models:
        parts = summary["models"][model]["judge_subscores"]
        rows.append([MODEL_LABEL.get(model, model)] + [parts[c] for c in CRITERIA] + [summary["models"][model]["judge_total"]])
    lines.append(table(["Modelo"] + [CRITERIA_LABEL[c] for c in CRITERIA] + ["Total /120"], rows))

    lines += ["", "## Comparación emparejada (juez Sol, misma oferta y prompt)", ""]
    rows = []
    for a, b in pairs:
        data = summary["paired"].get(f"{b} - {a}")
        if not data:
            continue
        rows.append([f"{MODEL_LABEL.get(b, b)} - {MODEL_LABEL.get(a, a)}", format(data["mean"], "+.2f"),
                     format(data["median"], "+.1f"), f"{data['wins']} / {data['ties']} / {data['losses']}",
                     f"{data['min']:+d} / {data['max']:+d}"])
    lines.append(table(["Diferencia", "Media", "Mediana", "Gana / Empata / Pierde", "Mín / Máx"], rows))

    lines += ["", "## Acuerdo entre jueces", ""]
    lines.append(table(["Métrica", "Valor"], [
        ["CV evaluados por ambos", agreement["n"]],
        ["Correlación de Pearson", agreement["pearson"]],
        ["Correlación de Spearman", agreement["spearman"]],
        ["Diferencia absoluta media /120", agreement["mean_abs_diff"]],
    ]))
    rows = []
    for model in models:
        rows.append([MODEL_LABEL.get(model, model), agreement["model_means_sol_judge"].get(model),
                     agreement["model_means_luna_judge"].get(model)])
    lines.append(table(["Modelo", "Media juez Sol", "Media juez Luna"], rows))

    lines += ["", "## Consistencia del juez (CV duplicado)", ""]
    rows = []
    for model in models:
        data = summary["duplicates"][model]
        rows.append([MODEL_LABEL.get(model, model), data["n"], data["mean_abs_delta"]])
    lines.append(table(["Modelo", "Duplicados", "Diferencia absoluta media /120"], rows))

    lines += ["", "## Estilos evaluados por el juez Sol", ""]
    rows = []
    for prompt in prompts:
        row = [prompt]
        for model in models:
            value = summary["models"][model]["by_prompt"].get(prompt, {}).get("judge_total")
            row.append(value if value is not None else "—")
        rows.append(row)
    lines.append(table(["Instrucción"] + [MODEL_LABEL.get(m, m) for m in models], rows))

    lines += ["", "## Métricas automáticas de calidad", ""]
    rows = []
    for model in models:
        data = summary["models"][model]
        rows.append([MODEL_LABEL.get(model, model), data["words"], data["bullets"], data["avg_words_bullet"],
                     f"{data['quantified_ratio']}%", f"{data['long_bullet_ratio']}%", data["forbidden_openers"],
                     data["buzz_per_100"], f"{data['repeated_4gram_ratio']}%", data["coverage_overall"],
                     f"{data['protected_ok_pct']}%"])
    lines.append(table(["Modelo", "Palabras", "Bullets", "Palabras/bullet", "Cuantificados", "Bullet largo",
                        "Aperturas prohibidas", "Buzz/100", "Repetición 4g", "Cobertura", "Campos protegidos"], rows))

    lines += ["", "## Idioma, fidelidad y revisión", ""]
    rows = []
    for model in models:
        data = summary["models"][model]
        rows.append([MODEL_LABEL.get(model, model), f"{data['language_match']} / {data['completed']}",
                     f"{data['mixed_voice']} / {data['spanish_cases']}", data["unsupported"], data["review_items"],
                     data["refine_applied"]])
    lines.append(table(["Modelo", "Idioma", "Voz mixta (ES)", "No respaldadas", "A revisar", "Dos pasadas"], rows))

    lines += ["", "## Nota del juez Sol por oferta", ""]
    rows = []
    for job in jobs:
        title = job_titles.get(job, job)
        if len(title) > 45:
            title = title[:42].rstrip() + "…"
        row = [title]
        for model in models:
            value = summary["models"][model]["by_job"].get(job, {}).get("judge_total")
            row.append(round(value / 1.2, 1) if value is not None else "—")
        rows.append(row)
    lines.append(table(["Oferta"] + [MODEL_LABEL.get(m, m) + " /100" for m in models], rows))

    lines += ["", "## Gráficos", ""]
    image_titles = {"summary": "Calidad, velocidad y costo", "heatmap": "Nota por oferta", "agreement": "Acuerdo entre jueces", "radar": "Perfil de criterios", "prompts": "Nota por instrucción"}
    for key, image_path in chart_paths.items():
        try:
            relative = image_path.relative_to(args.out.parent).as_posix()
        except ValueError:
            relative = image_path.as_posix()
        lines += [f"![{image_titles.get(key, key)}]({relative})", ""]

    lines += ["", "## Hallazgos", ""]
    best = max(models, key=lambda m: summary["models"][m]["judge_total"] or 0)
    fastest = min(models, key=lambda m: summary["models"][m]["median_seconds"] or 1e9)
    cheapest = min(models, key=lambda m: summary["models"][m]["median_cost"] or 1e9)
    lines.append(f"- Mejor nota del juez Sol: {MODEL_LABEL.get(best, best)} con {summary['models'][best]['judge_score_100']}/100.")
    lines.append(f"- Más rápido: {MODEL_LABEL.get(fastest, fastest)} con mediana {summary['models'][fastest]['median_seconds']} s; más barato: {MODEL_LABEL.get(cheapest, cheapest)} con USD {summary['models'][cheapest]['median_cost']} por CV.")
    sol_luna = summary["paired"].get("gpt-6.2-sol - gpt-6-luna")
    if sol_luna:
        lines.append(f"- Sol frente a Luna: {sol_luna['mean']:+.2f} puntos de 120, gana {sol_luna['wins']} y pierde {sol_luna['losses']} de {sol_luna['n']} pares.")
    lines.append(f"- Acuerdo entre jueces: Pearson {agreement['pearson']}, Spearman {agreement['spearman']}, diferencia media {agreement['mean_abs_diff']} sobre 120.")
    terra_luna = summary["paired"].get("gpt-6.1-terra - gpt-6-luna")
    sol_terra = summary["paired"].get("gpt-6.2-sol - gpt-6.1-terra")
    if terra_luna:
        lines.append(f"- Terra frente a Luna: {terra_luna['mean']:+.2f} puntos de 120, gana {terra_luna['wins']} y pierde {terra_luna['losses']} de {terra_luna['n']} pares.")
    if sol_terra:
        lines.append(f"- Sol frente a Terra: {sol_terra['mean']:+.2f} puntos de 120, gana {sol_terra['wins']} y pierde {sol_terra['losses']} de {sol_terra['n']} pares.")
    best_prompts = []
    for model in models:
        prompts_data = summary["models"][model]["by_prompt"]
        if prompts_data:
            prompt_name = max(prompts_data, key=lambda p: prompts_data[p]["judge_total"] or 0)
            prompt_value = prompts_data[prompt_name]["judge_total"]
            if prompt_value is not None:
                best_prompts.append(f"{MODEL_LABEL.get(model, model)}: {prompt_name} ({prompt_value:.1f})")
    if best_prompts:
        lines.append("- Mejor instrucción por modelo (juez Sol): " + "; ".join(best_prompts) + ".")
    offer_means = {}
    for job in jobs:
        values = [summary["models"][m]["by_job"].get(job, {}).get("judge_total") for m in models]
        values = [v for v in values if v is not None]
        if values:
            offer_means[job] = statistics.mean(values)
    if offer_means:
        best_offer = max(offer_means, key=offer_means.get)
        worst_offer = min(offer_means, key=offer_means.get)
        lines.append(f"- Mejor oferta para el perfil sintético: {job_titles.get(best_offer, best_offer)} ({offer_means[best_offer]:.1f}/120 de media); la más difícil: {job_titles.get(worst_offer, worst_offer)} ({offer_means[worst_offer]:.1f}/120).")
    if agreement["model_means_sol_judge"] and agreement["model_means_luna_judge"]:
        bias = {m: (agreement["model_means_sol_judge"].get(m) or 0) - (agreement["model_means_luna_judge"].get(m) or 0) for m in models}
        bias_text = "; ".join(f"{MODEL_LABEL.get(m, m)} {value:+.1f}" for m, value in bias.items())
        lines.append(f"- Diferencia Sol-juez menos Luna-juez por modelo (posible sesgo de familia): {bias_text}.")
    duplicate_deltas = [summary["duplicates"][m]["mean_abs_delta"] for m in models if summary["duplicates"][m]["mean_abs_delta"] is not None]
    if duplicate_deltas:
        lines.append(f"- Consistencia del juez Sol con CV duplicado: diferencia absoluta media {statistics.mean(duplicate_deltas):.1f} puntos de 120.")
    lines.append("- La nota absoluta no es comparable con la prueba anterior: cambió el conjunto de ofertas, la rúbrica (120 vs 100) y el juez principal.")
    lines += ["", "## Límites", "",
              "Es una simulación con un perfil sintético y un juez automático; no sustituye revisión humana ni predice contratación. Dos jueces de la misma familia reducen, pero no eliminan, el sesgo de evaluación. Las ofertas son reales, pero los CV y las identidades son ficticios."]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (exp / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (exp / "summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model", "completed", "language_match", "one_page", "median_seconds", "p90_seconds",
                         "median_cost", "judge_sol_120", "judge_sol_100", "judge_luna_100", "words", "bullets",
                         "quantified_ratio", "forbidden_openers", "buzz_per_100", "coverage_overall", "protected_ok_pct"])
        for model in models:
            d = summary["models"][model]
            writer.writerow([model, d["completed"], d["language_match"], d["one_page"], d["median_seconds"],
                             d["p90_seconds"], d["median_cost"], d["judge_total"], d["judge_score_100"],
                             d["judge2_score_100"], d["words"], d["bullets"], d["quantified_ratio"],
                             d["forbidden_openers"], d["buzz_per_100"], d["coverage_overall"], d["protected_ok_pct"]])
    with (exp / "per_cv.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model", "job", "prompt", "expected_language", "seconds", "complete", "language_match",
                         "cost_usd", "judge_sol_120", "judge_luna_120", "words", "bullets", "avg_words_bullet",
                         "quantified_ratio", "forbidden_openers", "buzz_per_100", "repeated_4gram_ratio",
                         "coverage_overall", "pages", "protected_ok", "unsupported", "review_items", "mixed_voice"])
        for row in records:
            writer.writerow([row["model"], row["job"], row["prompt"], row["expected_language"], row["seconds"],
                             row["complete"], row["language_match"], round(row["cost"], 6), row["judge_total"],
                             row["judge2_total"], row["words"], row["bullets"], row["avg_words_bullet"],
                             row["quantified_ratio"], row["forbidden_openers"], row["buzz_per_100"],
                             row["repeated_4gram_ratio"], row["coverage_overall"], row["pages"], row["protected_ok"],
                             row["unsupported"], row["review_items"], row["mixed_voice"]])
    print(json.dumps({"markdown": str(args.out), "summary": str(exp / "summary.json"), "cases": len(records),
                      "completed": len(done), "models": {m: {"score": summary["models"][m]["judge_score_100"],
                                                              "seconds": summary["models"][m]["median_seconds"],
                                                              "cost": summary["models"][m]["median_cost"]} for m in models}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
