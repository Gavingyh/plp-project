"""Local-only FinBERT inference in a short-lived process; never writes data."""

import argparse

import numpy as np
import pandas as pd

from aspects import embed
from config.model_version import FINETUNED, MODEL_VERSION
from train.evaluate import finetuned_probs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=FINETUNED[MODEL_VERSION]["models"])
    args = parser.parse_args()
    if not args.model:
        vectors = embed.embed_sentences(["DBS reported higher earnings."])
        if vectors.shape != (1, 768) or not np.isfinite(vectors).all():
            raise RuntimeError("Invalid FinBERT embeddings")
        print("PASS offline base FinBERT inference", flush=True)
        return
    sample = pd.DataFrame([{"text": "DBS reported higher earnings.", "aspect": "other"}])
    probabilities = finetuned_probs(args.model, sample)
    if probabilities.shape != (1, 3) or not np.isfinite(probabilities).all() or not np.allclose(probabilities.sum(axis=1), 1):
        raise RuntimeError(f"Invalid fine-tuned FinBERT output: {args.model}")
    print(f"PASS offline fine-tuned inference: {args.model}", flush=True)


if __name__ == "__main__":
    main()
