"""Build a portable skill/manual/local generator without any personal data.

Only explicit code/template/skill files are included. No .env, profiles, seeds,
history, generated PDFs or browser credentials are copied.
"""

import argparse
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "job-application-assistant"


def manual_text():
    intro = """# Instrucciones portables de postulaciones

Este documento es autocontenido: puedes pegarlo en otro chat o adjuntarlo junto a una campaña y un candidato verificados. No contiene datos reales de ninguna persona.

Mensaje de inicio sugerido:

> Usa estas instrucciones para gestionar la campaña de postulaciones indicada en campaign.json. Comprueba identidad, configuración y autorización; retoma el workspace existente. Controla el generador por CLI. Evalúa la oferta, genera el CV, revisa sus hechos y PDF, mejora cuando corresponda y completa la postulación dentro del alcance autorizado. Registra el resultado comprobado. Si solo te pido preparar o probar, conserva las solicitudes como borradores.

El paquete ZIP contiene `generator/` (código local sin perfiles personales) y `job-application-assistant/` (skill, referencias y muestras ficticias). Puedes usar el repositorio original que ya contiene la CLI o el generador del paquete. Crea su entorno Python, configura el proveedor autorizado y ajusta las rutas de campaign.json. La skill puede instalarse copiando su carpeta al directorio de skills del entorno; también puedes usar este documento sin instalarla.

La CLI genera/revisa/exporta CVs y mantiene el registro. La búsqueda, el llenado y el envío requieren un agente con herramientas de navegador en ese chat. El paquete no inicia por sí solo un robot de postulaciones ni trae sesiones de LinkedIn.

"""
    sections = [intro, SKILL.joinpath("SKILL.md").read_text(encoding="utf-8")]
    for name in ("workflow.md", "cli.md"):
        sections.append("\n\n---\n\n" + (SKILL / "references" / name).read_text(encoding="utf-8"))
    for path in sorted((SKILL / "assets").glob("*.json")):
        sections.append(f"\n\n## Formato incluido: {path.name}\n\n```json\n{path.read_text(encoding='utf-8').strip()}\n```\n")
    return "".join(sections)


def build(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manual = output / "INSTRUCCIONES_POSTULACIONES.md"
    text = manual_text()
    manual.write_text(text, encoding="utf-8")
    maintained_manual = ROOT / "docs" / "POSTULACIONES_PORTABLE.md"
    maintained_manual.parent.mkdir(parents=True, exist_ok=True)
    maintained_manual.write_text(text, encoding="utf-8")
    archive = output / "asistente-postulaciones-portable.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("INSTRUCCIONES_POSTULACIONES.md", text)
        bundle.writestr("generator/docs/POSTULACIONES_PORTABLE.md", text)
        for path in sorted(SKILL.rglob("*")):
            if path.is_file() and path.suffix in {".md", ".json", ".yaml"}:
                bundle.write(path, "job-application-assistant/" + path.relative_to(SKILL).as_posix())
        # Runtime code; importing personal seed data is lazy and never needed by CLI.
        for path in sorted((ROOT / "app").rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            if relative.startswith("app/data/") and relative != "app/data/__init__.py":
                continue
            bundle.write(path, "generator/" + relative)
        for folder, extensions in (("app/templates", {".html"}), ("app/static/icons", {".svg"})):
            for path in sorted((ROOT / folder).rglob("*")):
                if path.is_file() and path.suffix in extensions:
                    bundle.write(path, "generator/" + path.relative_to(ROOT).as_posix())
        for filename in ("requirements.txt", ".env.example", "AGENTS.md"):
            bundle.write(ROOT / filename, "generator/" + filename)
    return {"manual": str(manual), "archive": str(archive), "contains_personal_profiles": False}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--out", required=True, type=Path)
    args = cli.parse_args()
    print(json.dumps(build(args.out), ensure_ascii=False, indent=2))
