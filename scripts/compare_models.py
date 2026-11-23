"""Run the real CLI sequentially for each job/model, recording results for manual review."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = [
    ("openai", "gpt-6-luna"), ("openai", "gpt-6.1-terra"),
    ("openai", "gpt-6.2-sol"), ("deepseek", "deepseek-flash"),
    ("deepseek", "deepseek-v4-pro"), ("gemini", "gemini-2.5-flash"),
    ("gemini", "gemini-3.8-flash"),
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True, help="Initialized private candidate workspace")
    p.add_argument("--jobs", type=Path, required=True, help="Directory of UTF-8 .txt job descriptions")
    p.add_argument("--out", type=Path, required=True, help="New private output directory")
    p.add_argument("--profile", default="developer", choices=("developer", "bilingual_customer_service"))
    p.add_argument("--template", default="technical", choices=("technical", "modern", "classic", "bilingual"))
    args = p.parse_args()
    jobs = sorted(args.jobs.glob("*.txt"))
    if not jobs:
        p.error("No .txt job descriptions found")
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = []
    for job in jobs:
        digest = hashlib.sha256(job.read_bytes()).hexdigest()
        for provider, model in MODELS:
            run = {"job": job.name, "job_sha256": digest, "provider": provider, "model": model}
            folder = args.out / f"{job.stem}__{provider}__{model}"
            folder.mkdir()
            command = [sys.executable, "-m", "app.cli", "--workspace", str(args.workspace.resolve()),
                       "--profile", args.profile, "generate", "--job", str(job.resolve()),
                       "--provider", provider, "--model", model, "--template", args.template]
            started = time.monotonic()
            env = os.environ.copy()
            env["CV_USAGE_FILE"] = str((folder / "usage.jsonl").resolve())
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            run.update(elapsed_seconds=round(time.monotonic() - started, 2), success=result.returncode == 0)
            (folder / "generate.json").write_text(result.stdout, encoding="utf-8")
            (folder / "generate.stderr.txt").write_text(result.stderr, encoding="utf-8")
            if result.returncode == 0:
                try:
                    record = json.loads(result.stdout)["record_id"]
                    run["record_id"] = record
                    inspect = subprocess.run([sys.executable, "-m", "app.cli", "--workspace", str(args.workspace.resolve()),
                                              "--profile", args.profile, "inspect", "--record", record],
                                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
                    (folder / "inspect.json").write_text(inspect.stdout, encoding="utf-8")
                    (folder / "inspect.stderr.txt").write_text(inspect.stderr, encoding="utf-8")
                    run["inspect_success"] = inspect.returncode == 0
                except (ValueError, KeyError):
                    run["success"] = False
                    run["error"] = "CLI response lacked a valid record_id"
            manifest.append(run)
            (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"{job.name}: {provider}/{model}: {'OK' if run['success'] else 'ERROR'}", flush=True)
    return 0 if all(x["success"] and x.get("inspect_success") for x in manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
