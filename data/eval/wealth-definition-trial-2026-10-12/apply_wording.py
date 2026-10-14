"""Write the wealth wording the corpus was re-classified under into
config/aspects.yaml, and confirm the classifier's answer file for the config
is then the one that run filled. Run from the repository root."""
import subprocess, sys
sys.path.insert(0, "data/eval/wealth-definition-trial-2026-10-12")
import trial

EXPECTED = "llama3.1_8b.eef9b342.jsonl"
p = "config/aspects.yaml"; s = open(p).read()
old_wealth = 'llm_definition: "wealth management and private or premier banking: assets under management, wealth fee income, wealth targets"'
old_retail = 'llm_definition: "products and service as customers experience them: cards, cashback, savings accounts, fees, app or service outages, scams, applications"'
last_example = '  - {sentence: "The bank named a new chief technology officer.", aspect: other}\n'
if old_wealth in s:
    assert s.count(old_wealth) == 1 and s.count(old_retail) == 1 and s.count(last_example) == 1
    q = lambda t: t.replace('"', '\\"')
    s = s.replace(old_wealth, f'llm_definition: "{q(trial.NEW_DEFINITIONS["wealth_business"])}"')
    s = s.replace(old_retail, f'llm_definition: "{q(trial.NEW_DEFINITIONS["retail_banking_sentiment"])}"')
    extra = "".join(f'  - {{sentence: "{q(sent)}", aspect: {asp}}}\n' for sent, asp in trial.NEW_EXAMPLES)
    s = s.replace(last_example, last_example + extra)
    open(p, "w").write(s)
    print("config/aspects.yaml: wealth and retail definitions and two examples written")
else:
    print("config/aspects.yaml already holds the new wording")
out = subprocess.run([sys.executable, "-c", "from aspects.llm_classify import answer_cache_path as a; print(a('llama3.1:8b'))"],
                     capture_output=True, text=True).stdout.strip()
print("answer file for this config:", out)
sys.exit(0 if out.endswith(EXPECTED) else 1)
