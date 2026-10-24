"""The public model used to build and query the chatbot's search vectors."""

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
WIDTH = 384
# Only the PyTorch weights and tokenizer consumed by AutoModel/AutoTokenizer.
DOWNLOAD_PATTERNS = [
    "config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json",
    "special_tokens_map.json", "vocab.txt",
]
