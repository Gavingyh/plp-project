"""Tests for aspects/llm_classify.py with a fake model: no network."""

import pandas as pd

import aspects.llm_classify as lc

KEYS = ["dividend_policy", "asset_quality", "other"]


def test_prompt_lists_the_keys_and_holds_the_sentence():
    msgs = lc.build_messages("DBS raised its dividend.", KEYS)
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    for k in KEYS:
        assert f"- {k}:" in msgs[0]["content"]
    assert "net_interest_margin" not in msgs[0]["content"]          # examples only for listed keys
    assert "DBS raised its dividend." in msgs[1]["content"]


def test_parse_answer():
    assert lc.parse_answer('{"aspect": "asset_quality"}', KEYS) == "asset_quality"
    assert lc.parse_answer('Sure: {"aspect": "dividend_policy"} done', KEYS) == "dividend_policy"
    assert lc.parse_answer('{"aspect": "wealth"}', KEYS) is None      # not a key
    assert lc.parse_answer("", KEYS) is None


def test_retry_then_fallback_to_other():
    answers = iter(['{"aspect": "nope"}', '{"aspect": "asset_quality"}'])
    assert lc.classify("x", KEYS, chat=lambda m, msgs, k: next(answers)) == ("asset_quality", 2)
    assert lc.classify("x", KEYS, chat=lambda m, msgs, k: "garbage") == ("other", 0)


def test_rows_are_cached_and_resumed(tmp_path, monkeypatch):
    monkeypatch.setattr(lc, "aspect_keys", lambda: KEYS)
    calls = []

    def chat(model, msgs, keys):
        calls.append(msgs[1]["content"])
        return '{"aspect": "dividend_policy"}'

    rows = pd.DataFrame({"sentence_id": ["s1", "s2"], "text": ["a", "b"]})
    cache = str(tmp_path / "c.jsonl")
    first = lc.classify_rows(rows, chat=chat, cache_path=cache)
    second = lc.classify_rows(rows, chat=chat, cache_path=cache)
    assert len(calls) == 2                                             # second pass used the cache
    assert first["aspect"].tolist() == second["aspect"].tolist() == ["dividend_policy"] * 2


def test_evaluate():
    m = lc.evaluate(["a", "b", "a"], ["a", "a", "a"])
    assert m["top1_accuracy"] == 2 / 3 and m["n"] == 3


def test_think_is_sent_only_when_asked(monkeypatch):
    sent = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": '{"aspect": "other"}'}}

    monkeypatch.setattr(lc.requests, "post", lambda url, timeout, json: sent.append(json) or Resp())
    lc.ollama_chat("m", [], KEYS)
    lc.ollama_chat("m", [], KEYS, think=False)
    assert "think" not in sent[0] and sent[1]["think"] is False
    assert sent[1]["format"]["properties"]["aspect"]["enum"] == KEYS


def test_corpus_order_is_fixed_and_starts_with_the_preview_sample():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sentences (sentence_id TEXT, text TEXT)")
    conn.executemany("INSERT INTO sentences VALUES (?, ?)", [(f"s{i:03d}", f"t{i}") for i in range(200)])
    rows = lc.corpus_rows(conn, seed=2026)
    assert len(rows) == 200 and rows["sentence_id"].is_unique
    assert rows["sentence_id"].tolist() == lc.corpus_rows(conn, seed=2026)["sentence_id"].tolist()
    # aggregate.preview draws its sample of n the same way, so the first n rows match it
    base = pd.read_sql("SELECT sentence_id, text FROM sentences ORDER BY sentence_id", conn)
    assert rows["sentence_id"].head(30).tolist() == base.sample(n=30, random_state=2026)["sentence_id"].tolist()
    assert len(lc.corpus_rows(conn, seed=2026, limit=10)) == 10


def test_cache_file_is_named_by_the_prompt(monkeypatch):
    fp = lc.prompt_fingerprint(KEYS)
    assert len(fp) == 8 and fp == lc.prompt_fingerprint(KEYS)
    assert lc.answer_cache_path("llama3.1:8b", keys=KEYS).endswith(f"llama3.1_8b.{fp}.jsonl")
    assert lc.answer_cache_path("qwen3:4b", no_think=True, keys=KEYS).endswith(f"qwen3_4b-nothink.{fp}.jsonl")
    assert lc.prompt_fingerprint(KEYS + ["wealth_business"]) != fp           # an aspect added
    monkeypatch.setattr(lc, "EXAMPLES", lc.EXAMPLES[:-1])
    assert lc.prompt_fingerprint(KEYS) != fp                                 # an example dropped
    monkeypatch.undo()
    monkeypatch.setitem(lc.DEFINITIONS, "asset_quality", "loan quality only")
    assert lc.prompt_fingerprint(KEYS) != fp                                 # a definition reworded


def test_a_reworded_prompt_does_not_reuse_old_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(lc, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(lc, "aspect_keys", lambda: KEYS)
    prompts = []

    def chat(model, msgs, keys):
        prompts.append(msgs[0]["content"])
        return '{"aspect": "asset_quality"}'

    rows = pd.DataFrame({"sentence_id": ["s1"], "text": ["a"]})
    lc.classify_rows(rows, chat=chat)
    lc.classify_rows(rows, chat=chat)
    assert len(prompts) == 1                                                 # same prompt: cached
    monkeypatch.setitem(lc.DEFINITIONS, "asset_quality", "loan quality only")
    lc.classify_rows(rows, chat=chat)
    assert len(prompts) == 2 and "loan quality only" in prompts[1]           # new prompt: asked again
    assert len(list(tmp_path.glob("*.jsonl"))) == 2                          # old answers kept in their own file
