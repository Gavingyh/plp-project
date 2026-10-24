"""Read-only Docker integration checks; no hosted API calls or data collection."""

import argparse
from pathlib import Path
import subprocess
import sys

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--inference", action="store_true", help="also run local FinBERT and intent inference")
    mode.add_argument("--ui", action="store_true", help="also render all six Streamlit pages against the real API")
    args = parser.parse_args()
    api = "http://127.0.0.1:8000"
    for endpoint in ("/health", "/banks", "/aspects", "/coverage", "/chat/status", "/pipeline/sources", "/pipeline/runs"):
        response = requests.get(api + endpoint, timeout=30)
        response.raise_for_status()
        print(f"PASS {endpoint}", flush=True)
    for bank in ("DBS", "OCBC", "UOB"):
        response = requests.get(api + "/sentiment", params={"bank": bank}, timeout=30)
        response.raise_for_status()
        result = response.json()
        if result.get("insufficient_data") or not result.get("n"):
            raise RuntimeError(f"No served sentiment data for {bank}")
        print(f"PASS {bank} sentiment ({result['n']:,} sentences)", flush=True)
    response = requests.get("http://dashboard:8501/_stcore/health", timeout=10)
    response.raise_for_status()
    print("PASS Streamlit health", flush=True)
    from pipeline.stages import preflight

    preflight(["earnings", "sgx_research", "cna"])
    print("PASS PDF/CNA pipeline prerequisites and local models", flush=True)
    if args.ui:
        from streamlit.testing.v1 import AppTest

        for page in ("Overview", "Topics", "Trends", "Evidence", "Ask", "Data Management"):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py"))
            app.query_params["page"] = page
            app.run(timeout=120)
            if app.exception:
                raise RuntimeError(f"Streamlit {page}: {app.exception[0].message}")
            print(f"PASS Streamlit {page} render", flush=True)
    if args.inference:
        # Release all FinBERT/PyTorch test memory before loading Ollama's 8B model.
        subprocess.run([sys.executable, "-m", "docker.model_smoke"], check=True)
        from config.model_version import FINETUNED, MODEL_VERSION
        for folder in FINETUNED[MODEL_VERSION]["models"]:
            subprocess.run([sys.executable, "-m", "docker.model_smoke", "--model", folder], check=True)
        from chatbot.intent import classify_intent

        if classify_intent("What is the overall sentiment on DBS?") != "in_scope":
            raise RuntimeError("The local intent classifier did not return in_scope")
        print("PASS local Ollama intent inference", flush=True)
    print("All Docker smoke checks passed. No hosted-model requests were sent.", flush=True)


if __name__ == "__main__":
    main()
