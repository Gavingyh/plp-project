"""
The sentiment model whose scores the index, the API and the chatbot read.

aspect_sentiment and sentiment_index can hold scores from more than one model
side by side (sentiment/score.py), so a before/after comparison stays
possible. Every reader filters on this version so the two never mix: without
the filter, a second model's rows would double every sentence and every index
cell. Change it in the same commit that re-scores the corpus with a new model.

This is the version the readers serve, not a setting for the scorer:
sentiment/score.py always tags its rows "finbert-base-zeroshot-v1", the model
it runs, so changing this constant can never relabel base-FinBERT scores as
another model's. Kept apart from sentiment/score.py, which imports torch, so
that the API and the chatbot can read it cheaply.
"""

MODEL_VERSION = "finbert-base-zeroshot-v1"
