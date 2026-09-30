"""
The torch device every model in the project runs on: CUDA when present (a
Colab or lab GPU), then Apple's MPS, then CPU. One function, so the three
places that load a model can't disagree; before it, each checked only MPS,
and a CUDA machine silently ran on CPU unless the code was patched by hand.
"""

import torch


def best_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"
