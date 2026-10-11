"""Tests for preprocess/bank_ner.py: resolution, recognition on the hard cases, scoring, the gold sheet."""

import sqlite3

import pandas as pd
import pytest

import preprocess.bank_ner as ner


@pytest.mark.parametrize("mention,expected", [
    ("DBS", "DBS"), ("dbs", "DBS"), ("POSB", "DBS"),
    ("Bank of Singapore", "OCBC"), ("Great Eastern", "OCBC"), ("Oversea-Chinese", "OCBC"),
    ("UOB", "UOB"), ("United Overseas Bank", "UOB"),
    ("UOB Kay Hian", ner.NOT_BANK), ("UOBKH", ner.NOT_BANK), ("DBS Vickers", "DBS"),
    ("Aston Martin DBS", ner.NOT_BANK), ("deep brain stimulation", ner.NOT_BANK),
    ("Citibank", None), ("Singapore", None),
    ("Development Bank of Singapore", "DBS"), ("The Development Bank of Singapore", "DBS"),
    ("Dumbest Bank of Singapore", "DBS"),
    ("PayLah", "DBS"), ("paylah", "DBS"), ("digibank", "DBS"),
    ("TMRW", "UOB"), ("tmrw", None), ("Tmrw", None),
])
def test_resolution_table(mention, expected):
    assert ner.resolve(mention) == expected


@pytest.mark.parametrize("text,expected", [
    ("I opened a POSB account last year.", ["DBS"]),                    # POSB is DBS's retail brand
    ("my dbs card got declined again", ["DBS"]),                       # lowercase Reddit text
    ("UOB Kay Hian raised its target for OCBC.", ["OCBC"]),            # the broker isn't UOB
    ("I bought shares on DBS Vickers and UOB.", ["DBS", "UOB"]),      # DBS Vickers counts as DBS
    ("I only use DBS Vickers for SGX trades.", ["DBS"]),
    ("Great Eastern lifted group earnings.", ["OCBC"]),
    ("He drives an Aston Martin DBS.", []),
    ("DBS, OCBC and UOB all reported higher profit.", ["DBS", "OCBC", "UOB"]),
    ("The Development Bank of Singapore was founded in 1968.", ["DBS"]),   # DBS's old name, not OCBC's private bank
    ("Dumbest Bank of Singapore strikes again with another outage.", ["DBS"]),
    ("Bank of Singapore hired a new head of wealth planning.", ["OCBC"]),   # the private bank is still OCBC's
    ("PayLah is down again this morning.", ["DBS"]),                    # an app named alone
    ("I can't log in to digibank since last night.", ["DBS"]),
    ("TMRW keeps crashing when I open it.", ["UOB"]),
    ("These include our mobile-only digital bank, TMRW, in Indonesia.", ["UOB"]),
    ("I will transfer the money tmrw morning.", []),                    # "tomorrow", not the app
    ("see you Tmrw at the branch", []),
])
def test_recognition_on_the_hard_cases(text, expected):
    assert ner.banks_in(text) == expected


def test_scores_count_sentence_bank_pairs():
    gold = [{"DBS"}, {"OCBC", "UOB"}, set()]
    pred = [{"DBS"}, {"OCBC"}, {"UOB"}]
    m = ner.prf(gold, pred)
    assert (m["precision"], m["recall"]) == (2 / 3, 2 / 3)
    assert m["exact"] == 1 / 3


def test_gold_cells_parse_and_reject_unknown_banks():
    assert ner.parse_banks("dbs; UOB") == {"DBS", "UOB"}
    assert ner.parse_banks("") == set()
    with pytest.raises(ValueError, match="unknown"):
        ner.parse_banks("Citibank")


def test_gold_sheet_is_stratified_blank_and_without_duplicates():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sentences (sentence_id TEXT, source TEXT, text TEXT)")
    rows = [(f"p{i}", "arctic_shift", f"POSB account number {i}") for i in range(40)]
    rows += [(f"r{i}", "earnings", f"Net profit rose {i}%") for i in range(60)]
    rows += [("dup", "arctic_shift", "POSB account number 1")]                  # same text as p1
    conn.executemany("INSERT INTO sentences VALUES (?, ?, ?)", rows)
    sheet = ner.draw_gold(conn)
    assert sheet["sentence_id"].is_unique and sheet["text"].is_unique
    assert (sheet["case"] == "posb").sum() == 30
    assert (sheet["gold_banks"] == "").all() and (sheet["annotator"] == "").all()
    assert "alias" not in sheet.columns and "ner" not in sheet.columns        # no tool output shown


def test_evaluate_needs_labelled_rows_and_compares_both_methods():
    gold = pd.DataFrame({"case": ["posb", "kay_hian"], "text": ["I use POSB.", "UOB Kay Hian says buy."],
                         "gold_banks": ["DBS", ""], "annotator": ["labelling", "labelling"]})
    res = ner.evaluate(gold)
    overall = res[res["case"] == "ALL"].set_index("method")
    assert overall.loc["NER", "exact"] == 1.0
    assert overall.loc["alias matching", "exact"] == 0.5                     # finds POSB, takes the broker as UOB
    with pytest.raises(ValueError, match="no labelled rows"):
        ner.evaluate(gold.assign(annotator=""))


@pytest.mark.parametrize("text,expected", [
    ("Thinking of DBS/ bank stocks and MMF.", ["DBS"]),
    ("2K SGD monthly DCA alternating between VWRA and OCBC+Sti Eng.", ["OCBC"]),
    ("Complete list of UOB$ merchants", ["UOB"]),
    ("Only have 1 SG stock in my portfolio… D05.SI", ["DBS"]),
    ("For more information, please visit www.ocbc.com.", ["OCBC"]),
    ("DBS Vickers/ UOB Kay Hian both charge less now", ["DBS"]),  # DBS Vickers is DBS; the fallback doesn't undo UOB Kay Hian
])
def test_fallback_catches_names_glued_to_punctuation(text, expected):
    assert ner.banks_in(text) == expected


def test_a_bank_name_joined_to_a_number_is_found():
    """'OCBC360' is the OCBC 360 account (Opus reference rater)."""
    assert ner.banks_in("Transferring money from DBS/POSB into OCBC360.") == ["DBS", "OCBC"]
    assert ner.banks_in("already maxing out on my ocbc360") == ["OCBC"]
