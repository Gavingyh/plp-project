"""Trial of the aspect model's prompt with the 10 Oct wealth rule written in:
wealth means the priority and private tiers and the wealth segment's figures;
investment products an ordinary customer can hold are retail. Classifies the
labelled sentences with the new wording and compares it with the wording the
corpus was classified under, against two references: the LLM rater's aspects,
made under the new rules, and people's aspects on the first round, made under
the old reading. Nothing in config/ or the database changes: the new wording
is set in this process only, and its answers go to their own cache file.

  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 data/eval/wealth-definition-trial-2026-10-12/trial.py
"""
import json, os, sqlite3, sys
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
import pandas as pd
import aspects.llm_classify as llm

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = llm.DEFAULT_MODEL
OLD_CACHE = llm.answer_cache_path(MODEL)

NEW_DEFINITIONS = {
    "wealth_business": "the bank's wealth business: its priority and private banking tiers (such as DBS Treasures, "
                       "OCBC Premier, UOB Privilege) and what they offer, assets under management, wealth management "
                       "fee income, wealth targets. Not an investment product any customer can hold",
    "retail_banking_sentiment": "products and service as ordinary customers experience them: cards, cashback, savings "
                                "accounts, loans and mortgages, unit trusts, brokerage accounts, regular savings plans, "
                                "insurance, robo-advisers, fees, app or service outages, scams, applications",
}
NEW_EXAMPLES = [("The sales charge on the unit trust I bought through the bank's app was 2%.", "retail_banking_sentiment"),
                ("Their priority banking tier gives you a relationship manager and lounge access.", "wealth_business")]


def answers(path):
    out = {}
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            out[r["sentence_id"]] = r["aspect"]
    return out


def main():
    rater = pd.read_csv("data/labeled/llm_rater/rules-2026-10-10/rater_labels.csv")
    people = pd.read_csv("data/labeled/candidates.csv").drop_duplicates("sentence_id")[["sentence_id", "aspect"]]
    conn = sqlite3.connect("file:data/plp.db?mode=ro", uri=True)
    texts = pd.read_sql("SELECT sentence_id, text FROM sentences", conn)
    conn.close()
    rows = rater.merge(texts, on="sentence_id").drop_duplicates("sentence_id")
    print(f"labelled rows {rater['sentence_id'].nunique()}, with text in the database {len(rows)}", flush=True)

    old = answers(OLD_CACHE)
    llm.DEFINITIONS = {**llm.DEFINITIONS, **NEW_DEFINITIONS}
    llm.EXAMPLES = llm.EXAMPLES + [e for e in NEW_EXAMPLES if e not in llm.EXAMPLES]
    new_cache = llm.answer_cache_path(MODEL)
    assert new_cache != OLD_CACHE
    print(f"old wording: {OLD_CACHE}\nnew wording: {new_cache}", flush=True)
    res = llm.classify_rows(rows[["sentence_id", "text"]], MODEL, cache_path=new_cache)
    new = dict(zip(res["sentence_id"], res["aspect"]))

    rows = rows[rows["sentence_id"].isin(old)].copy()
    rows["old"], rows["new"] = rows["sentence_id"].map(old), rows["sentence_id"].map(new)
    rows = rows.merge(people.rename(columns={"aspect": "people"}), on="sentence_id", how="left")
    out = {"rows": len(rows), "invalid_new": int((res["attempts"] == 0).sum()),
           "changed": int((rows["old"] != rows["new"]).sum()),
           "moves": {f"{a} -> {b}": n for (a, b), n in Counter(zip(rows["old"], rows["new"])).most_common() if a != b}}
    wr = {"wealth_business", "retail_banking_sentiment"}
    for ref, sub in (("rater_aspect", rows), ("people", rows[rows["people"].notna()])):
        focus = sub[sub[ref].isin(wr) | sub["old"].isin(wr) | sub["new"].isin(wr)]
        out[ref] = {"n": len(sub),
                    "old_agree": round(float((sub["old"] == sub[ref]).mean()), 4),
                    "new_agree": round(float((sub["new"] == sub[ref]).mean()), 4),
                    "n_wealth_or_retail": len(focus),
                    "old_agree_wealth_or_retail": round(float((focus["old"] == focus[ref]).mean()), 4),
                    "new_agree_wealth_or_retail": round(float((focus["new"] == focus[ref]).mean()), 4),
                    "reference_wealth_rows": int((sub[ref] == "wealth_business").sum()),
                    "old_called_wealth": int((sub["old"] == "wealth_business").sum()),
                    "new_called_wealth": int((sub["new"] == "wealth_business").sum()),
                    "old_wealth_right": int(((sub["old"] == "wealth_business") & (sub[ref] == "wealth_business")).sum()),
                    "new_wealth_right": int(((sub["new"] == "wealth_business") & (sub[ref] == "wealth_business")).sum())}
    by_sheet = rows.groupby("sheet").apply(lambda g: pd.Series({
        "n": len(g), "old_agree": round((g["old"] == g["rater_aspect"]).mean(), 4),
        "new_agree": round((g["new"] == g["rater_aspect"]).mean(), 4)}), include_groups=False)
    out["rater_aspect_by_sheet"] = by_sheet.to_dict("index")
    json.dump(out, open(os.path.join(HERE, "results.json"), "w"), indent=2)
    rows[["sentence_id", "sheet", "rater_aspect", "people", "old", "new"]].to_csv(os.path.join(HERE, "answers.csv"), index=False)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
