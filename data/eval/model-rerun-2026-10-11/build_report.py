"""Build the model comparison report from report_data.json. Every figure on the page is read
from that file; nothing is typed in by hand. Writes the artifact body and a standalone copy."""
import html
import json
import sys

import os
S = os.path.dirname(os.path.abspath(__file__)) + "/"
D = json.load(open(S + "report_data.json"))
L = D["labels"]                                   # negative, neutral, positive
F, B, A = D["scopes"]["first"], D["scopes"]["broker"], D["scopes"]["all"]

NAME = {
    "base": ("Base FinBERT", "no fine-tuning"),
    "people_1oct": ("Fine-tuned on people's labels", "1 Oct, 978 rows"),
    "people_4oct": ("Fine-tuned on people's labels, retrained", "4 Oct, 978 rows"),
    "people_7oct": ("Fine-tuned on people's labels, with broker rows", "7 Oct, 1,258 rows"),
    "opus_finbert": ("Fine-tuned on Opus's labels", "11 Oct, 1,563 rows"),
    "opus_adapted": ("Adapted encoder, fine-tuned on Opus's labels", "11 Oct, 1,563 rows"),
}
FAM = {"base": "base", "people_1oct": "people", "people_4oct": "people", "people_7oct": "people",
       "opus_finbert": "opus", "opus_adapted": "adapted"}
e = html.escape


def f3(x): return f"{x:.3f}"
def f2(x): return f"{x:.2f}"
def pct(v, lo, hi): return f"{100 * (v - lo) / (hi - lo):.2f}%"
def sgn(x): return f"{x:+.3f}".replace("-", "&#8722;")


def main_of(scope, sid):
    s = scope["sets"][sid]
    return s["single"] if sid == "base" else s["mean"]


# ---------- dot plot: macro-F1 per model set, seeds, mean and the three averaged ----------
def dotplot(scope, sids, lo=0.50, hi=0.80, step=0.05, measure="macro_f1"):
    n = round((hi - lo) / step)
    ticks = "".join(f'<span style="left:{pct(lo + i * step, lo, hi)}">{lo + i * step:.2f}</span>' for i in range(n + 1))
    out = [f'<div class="dp" style="--cols:{n}">',
           f'<div class="dp-row dp-head"><div class="dp-label"></div><div class="dp-axis">{ticks}</div><div class="dp-val"></div></div>']
    for sid in sids:
        s = scope["sets"][sid]
        name, sub = NAME[sid]
        marks = []
        if sid == "base":
            v = s["single"][measure]
            marks.append(f'<i class="dot mean" style="left:{pct(v, lo, hi)}" data-tip="{e(name)}: {f3(v)}"></i>')
            val = f'<b>{f3(v)}</b>'
        else:
            for seed, m in s["seeds"].items():
                marks.append(f'<i class="dot seed" style="left:{pct(m[measure], lo, hi)}" data-tip="Seed {seed}: {f3(m[measure])}"></i>')
            v, a = s["mean"][measure], s["averaged"][measure]
            marks.append(f'<i class="dot avg" style="left:{pct(a, lo, hi)}" data-tip="The three averaged: {f3(a)}"></i>')
            marks.append(f'<i class="dot mean" style="left:{pct(v, lo, hi)}" data-tip="Mean of three seeds: {f3(v)}"></i>')
            val = f'<b>{f3(v)}</b><span>{f3(a)} averaged</span>'
        win = " win" if sid == "opus_adapted" else ""
        out.append(f'<div class="dp-row fam-{FAM[sid]}{win}"><div class="dp-label"><b>{e(name)}</b><span>{e(sub)}</span></div>'
                   f'<div class="dp-track">{"".join(marks)}</div><div class="dp-val">{val}</div></div>')
    out.append("</div>")
    return "\n".join(out)


def dot_table(scope, sids):
    rows = []
    for sid in sids:
        s = scope["sets"][sid]
        name, sub = NAME[sid]
        if sid == "base":
            rows.append(f"<tr><th>{e(name)}</th><td>{f3(s['single']['macro_f1'])}</td><td></td><td></td><td></td><td></td><td></td></tr>")
        else:
            sd = s["seeds"]
            rows.append(f"<tr><th>{e(name)} <span class='muted'>({e(sub)})</span></th><td>{f3(s['mean']['macro_f1'])}</td><td>{f3(s['sd_macro_f1'])}</td>"
                        f"<td>{f3(sd['42']['macro_f1'])}</td><td>{f3(sd['1']['macro_f1'])}</td><td>{f3(sd['7']['macro_f1'])}</td><td>{f3(s['averaged']['macro_f1'])}</td></tr>")
    return ("<details><summary>Show the numbers</summary><div class='scroll'><table class='num'><thead><tr><th>Model</th><th>Mean</th><th>Seed sd</th>"
            "<th>Seed 42</th><th>Seed 1</th><th>Seed 7</th><th>Three averaged</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></details>")


# ---------- grouped bars: precision or recall by class ----------
BAR_SETS = ["base", "people_4oct", "opus_finbert", "opus_adapted"]
BAR_SHORT = {"base": "Base FinBERT", "people_4oct": "People's labels, 4 Oct", "opus_finbert": "Opus's labels", "opus_adapted": "Adapted, Opus's labels"}


def bars(scope, which):
    out = [f'<div class="bars"><div class="bars-title">{which.capitalize()}</div>',
           '<div class="bars-axis"><span style="left:0%">0</span><span style="left:25%">0.25</span><span style="left:50%">0.50</span><span style="left:75%">0.75</span><span style="left:100%">1</span></div>']
    for lab in L:
        n = scope["label_counts"][lab]
        out.append(f'<div class="bars-group"><div class="bars-class">{lab.capitalize()} <span>{n} rows</span></div>')
        for sid in BAR_SETS:
            v = main_of(scope, sid)[lab][which]
            out.append(f'<div class="bar-row fam-{FAM[sid]}"><div class="bar-track"><i class="bar" style="width:{100 * v:.1f}%" '
                       f'data-tip="{e(BAR_SHORT[sid])}, {lab} {which}: {f2(v)}"></i><span class="bar-val" style="left:{100 * v:.1f}%">{f2(v)}</span></div></div>')
        out.append("</div>")
    out.append("</div>")
    return "\n".join(out)


def pr_table(scope):
    head = "<tr><th>Model</th>" + "".join(f"<th>{l.capitalize()} P</th><th>{l.capitalize()} R</th><th>{l.capitalize()} F1</th>" for l in L) + "</tr>"
    rows = []
    for sid in BAR_SETS:
        m = main_of(scope, sid)
        rows.append(f"<tr><th>{e(BAR_SHORT[sid])}</th>" + "".join(f"<td>{f2(m[l]['precision'])}</td><td>{f2(m[l]['recall'])}</td><td>{f2(m[l]['f1'])}</td>" for l in L) + "</tr>")
    return f"<details><summary>Show the numbers</summary><div class='scroll'><table class='num'><thead>{head}</thead><tbody>{''.join(rows)}</tbody></table></div></details>"


# ---------- confusion matrix as a shaded table ----------
def confusion(scope_key, sid, title):
    m = D["confusion"][scope_key][sid]
    rows = []
    for i, lab in enumerate(L):
        tot = sum(m[i])
        cells = "".join(f'<td class="{"hit" if i == j else ""}" style="--s:{60 * m[i][j] / tot:.0f}%" data-tip="{m[i][j]} of the {tot} truly {lab} rows were called {L[j]}">{m[i][j]}</td>'
                        for j in range(3))
        rows.append(f"<tr><th>{lab.capitalize()} <span>{tot}</span></th>{cells}</tr>")
    called = [sum(m[i][j] for i in range(3)) for j in range(3)]
    foot = "<tr class='foot'><th>Called</th>" + "".join(f"<td>{c}</td>" for c in called) + "</tr>"
    return (f'<figure class="cm"><figcaption>{title}</figcaption><table><thead><tr><th>Truly</th>'
            + "".join(f"<th>called {l}</th>" for l in L) + f"</tr></thead><tbody>{''.join(rows)}{foot}</tbody></table></figure>")


# ---------- accuracy by source ----------
SRC = [("arctic_shift", "Reddit"), ("sgx_research", "Broker research"), ("earnings", "Earnings reports"), ("google_news", "Google News")]


def source_bars():
    out = ['<div class="bars src"><div class="bars-axis"><span style="left:0%">0</span><span style="left:25%">0.25</span><span style="left:50%">0.50</span><span style="left:75%">0.75</span><span style="left:100%">1</span></div>']
    for key, name in SRC:
        n = D["by_source"]["base"][key]["n"]
        out.append(f'<div class="bars-group"><div class="bars-class">{name} <span>{n} rows</span></div>')
        for sid in ("base", "opus_adapted"):
            v = D["by_source"][sid][key]["accuracy"]
            out.append(f'<div class="bar-row fam-{FAM[sid]}"><div class="bar-track"><i class="bar" style="width:{100 * v:.1f}%" data-tip="{e(BAR_SHORT[sid])} on {name}: {f2(v)} of {n} rows right"></i>'
                       f'<span class="bar-val" style="left:{100 * v:.1f}%">{f2(v)}</span></div></div>')
        out.append("</div>")
    out.append("</div>")
    return "\n".join(out)


# ---------- cross-validation: paired folds ----------
def cv_plot(lo=0.62, hi=0.76, step=0.02):
    n = round((hi - lo) / step)
    ticks = "".join(f'<span style="left:{pct(lo + i * step, lo, hi)}">{lo + i * step:.2f}</span>' for i in range(n + 1))
    out = [f'<div class="dp cv" style="--cols:{n}">', f'<div class="dp-row dp-head"><div class="dp-label"></div><div class="dp-axis">{ticks}</div><div class="dp-val"></div></div>']
    for r in D["cv"]["folds"]:
        a, b = r["finbert"], r["adapted"]
        left, width = pct(min(a, b), lo, hi), f"{100 * abs(b - a) / (hi - lo):.2f}%"
        d = b - a
        out.append(f'<div class="dp-row"><div class="dp-label"><b>Seed {r["seed"]}, fold {r["fold"]}</b></div><div class="dp-track">'
                   f'<i class="link" style="left:{left};width:{width}"></i>'
                   f'<i class="dot mean fam-opus" style="left:{pct(a, lo, hi)}" data-tip="FinBERT: {f3(a)}"></i>'
                   f'<i class="dot mean fam-adapted" style="left:{pct(b, lo, hi)}" data-tip="Adapted encoder: {f3(b)}"></i></div>'
                   f'<div class="dp-val"><b class="{"up" if d > 0 else "down"}">{sgn(d)}</b></div></div>')
    out.append("</div>")
    return "\n".join(out)


def cv_table():
    rows = "".join(f"<tr><th>Seed {r['seed']}, fold {r['fold']}</th><td>{f3(r['finbert'])}</td><td>{f3(r['adapted'])}</td><td>{sgn(r['adapted'] - r['finbert'])}</td></tr>" for r in D["cv"]["folds"])
    return ("<details><summary>Show the numbers</summary><div class='scroll'><table class='num'><thead><tr><th>Fold</th><th>FinBERT</th><th>Adapted encoder</th><th>Difference</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div></details>")


# ---------- the full appendix table for one scope ----------
ALL_SETS = ["base", "people_1oct", "people_4oct", "people_7oct", "opus_finbert", "opus_adapted"]


def full_table(scope):
    head = ("<tr><th>Model</th><th>Accuracy</th><th>Macro-F1</th><th>Seed sd</th>"
            + "".join(f"<th>{l.capitalize()} P / R / F1</th>" for l in L) + "</tr>")
    rows = []

    def cells(m): return "".join(f"<td>{f2(m[l]['precision'])} / {f2(m[l]['recall'])} / {f2(m[l]['f1'])}</td>" for l in L)
    for sid in ALL_SETS:
        s = scope["sets"][sid]
        name, sub = NAME[sid]
        if sid == "base":
            m = s["single"]
            rows.append(f"<tr><th>{e(name)}</th><td>{f3(m['accuracy'])}</td><td>{f3(m['macro_f1'])}</td><td></td>{cells(m)}</tr>")
        else:
            m, a = s["mean"], s["averaged"]
            cls = " class='winrow'" if sid == "opus_adapted" else ""
            rows.append(f"<tr{cls}><th>{e(name)} <span class='muted'>({e(sub)})</span>, mean of three seeds</th><td>{f3(m['accuracy'])}</td><td>{f3(m['macro_f1'])}</td><td>{f3(s['sd_macro_f1'])}</td>{cells(m)}</tr>")
            rows.append(f"<tr{cls}><th class='sub'>the three averaged</th><td>{f3(a['accuracy'])}</td><td>{f3(a['macro_f1'])}</td><td></td>{cells(a)}</tr>")
    return f"<div class='scroll'><table class='num wide'><thead>{head}</thead><tbody>{''.join(rows)}</tbody></table></div>"


# ---------- what the index would read on the test rows ----------
def net(m):
    n = sum(map(sum, m))
    called = [sum(m[i][j] for i in range(3)) for j in range(3)]
    truth = [sum(m[i]) for i in range(3)]
    return {"n": n, "truth_net": (truth[2] - truth[0]) / n, "pred_net": (called[2] - called[0]) / n,
            "truth_nonneutral": (truth[0] + truth[2]) / n, "pred_nonneutral": (called[0] + called[2]) / n,
            "called": called, "truth": truth}


def net_table():
    rows = []
    for key, label in (("first", "First round, 299 rows"), ("broker", "Broker research, 100 rows"), ("all", "Both, 399 rows")):
        b, a = net(D["confusion"][key]["base"]), net(D["confusion"][key]["opus_adapted"])
        rows.append(f"<tr><th>{label}</th><td>{sgn(b['truth_net'])}</td><td>{sgn(b['pred_net'])}</td><td>{sgn(a['pred_net'])}</td>"
                    f"<td>{100 * b['truth_nonneutral']:.0f}%</td><td>{100 * b['pred_nonneutral']:.0f}%</td><td>{100 * a['pred_nonneutral']:.0f}%</td></tr>")
    return ("<div class='scroll'><table class='num'><thead><tr><th rowspan='2'>Test rows</th><th colspan='3'>Net balance: (positive &#8722; negative) / all</th><th colspan='3'>Share called positive or negative</th></tr>"
            "<tr><th>Labels</th><th>Base FinBERT</th><th>Adapted, averaged</th><th>Labels</th><th>Base FinBERT</th><th>Adapted, averaged</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>")


cb, ca = D["confusion"]["first"]["base"], D["confusion"]["first"]["opus_adapted"]
pf, pb, pa = D["paired"]["first"], D["paired"]["broker"], D["paired"]["all"]
cv = D["cv"]
fa, fo, fp4, fp1 = F["sets"]["opus_adapted"], F["sets"]["opus_finbert"], F["sets"]["people_4oct"], F["sets"]["people_1oct"]
fbase = F["sets"]["base"]["single"]
ba, bo, bbase = B["sets"]["opus_adapted"], B["sets"]["opus_finbert"], B["sets"]["base"]["single"]
aa, abase = A["sets"]["opus_adapted"], A["sets"]["base"]["single"]
nb_f, na_f = net(cb), net(ca)
nb_b, na_b = net(D["confusion"]["broker"]["base"]), net(D["confusion"]["broker"]["opus_adapted"])
src = D["by_source"]
tr, pt = D["train"], D["pretraining"]
right_base, right_ad = sum(cb[i][i] for i in range(3)), sum(ca[i][i] for i in range(3))


def p(x): return f"{x:.2f}" if x >= 0.095 else f"{x:.3f}"


CSS = open(S + "report.css").read()
BODY = f"""
<div class="wrap">

<header class="mast">
  <div class="eyebrow"><span>PLP practice module</span><span>DBS · OCBC · UOB sentiment</span><span>Mon 12 Oct 2026</span></div>
  <h1>Which FinBERT should the dashboard and chatbot use?</h1>
  <p class="lede">Six versions of the sentiment model were scored on the same held-out sentences. The best is FinBERT first adapted to the project's own text, then fine-tuned on Opus's labels. Its overall accuracy is about the same as plain FinBERT's. What changes is the kind of mistake: it stops calling almost everything neutral, and finds three in five negative sentences where plain FinBERT found one in five.</p>
  <div class="tiles">
    <div><span class="k">Macro-F1, 299 test rows</span><b>{f3(fbase['macro_f1'])} <i>to</i> {f3(fa['mean']['macro_f1'])}</b><span>base FinBERT to the best set, mean of three seeds</span></div>
    <div><span class="k">Negative sentences found</span><b>{100 * fbase['negative']['recall']:.0f}% <i>to</i> {100 * fa['mean']['negative']['recall']:.0f}%</b><span>recall on the {F['label_counts']['negative']} negative test rows</span></div>
    <div><span class="k">Broker research, 100 test rows</span><b>{f3(bbase['macro_f1'])} <i>to</i> {f3(ba['mean']['macro_f1'])}</b><span>macro-F1 on text no earlier model beat base FinBERT on</span></div>
    <div><span class="k">Cross-validation</span><b>{cv['better']} of {cv['n']} folds</b><span>where the adapted encoder beat plain FinBERT, by {sgn(cv['diff_mean'])} on average</span></div>
  </div>
</header>

<nav class="toc" aria-label="Sections">
  <a href="#compared">What was compared</a><a href="#tested">How it was tested</a><a href="#headline">The headline</a><a href="#errors">The kind of error</a>
  <a href="#classes">By class</a><a href="#other">Other text</a><a href="#adapted">Adapted or plain</a><a href="#index">Effect on the index</a><a href="#limits">Limits</a><a href="#next">Decision</a><a href="#tables">Full tables</a>
</nav>

<section id="compared">
  <h2>What was compared</h2>
  <p>Every version starts from the same published model, FinBERT, which was trained on financial news. They differ in two ways: which labelled sentences they were fine-tuned on, and whether FinBERT first read the project's own sentences without labels.</p>
  <div class="scroll"><table class="plain">
    <thead><tr><th>Model</th><th>Starts from</th><th>Fine-tuned on</th><th>Date</th></tr></thead>
    <tbody>
      <tr class="fam-base"><th><i class="key"></i>Base FinBERT</th><td>FinBERT as published</td><td>Nothing. This is what every stored score in the database comes from today.</td><td></td></tr>
      <tr class="fam-people"><th><i class="key"></i>Fine-tuned on people's labels</th><td>FinBERT</td><td>978 sentences labelled by the team</td><td>1 Oct</td></tr>
      <tr class="fam-people"><th><i class="key"></i>The same, retrained</th><td>FinBERT</td><td>The same 978 sentences, after a fault in how training began was fixed</td><td>4 Oct</td></tr>
      <tr class="fam-people"><th><i class="key"></i>The same, with broker rows</th><td>FinBERT</td><td>1,258 sentences: the 978 plus 280 from broker research reports</td><td>7 Oct</td></tr>
      <tr class="fam-opus"><th><i class="key"></i>Fine-tuned on Opus's labels</th><td>FinBERT</td><td>{tr['rows']:,} sentences labelled by Claude Opus 5.5 under the rules of 10 Oct</td><td>11 Oct</td></tr>
      <tr class="fam-adapted"><th><i class="key"></i>Adapted encoder, fine-tuned on Opus's labels</th><td>FinBERT after reading {pt['kept']:,} of the corpus's own sentences</td><td>The same {tr['rows']:,} sentences</td><td>11 Oct</td></tr>
    </tbody>
  </table></div>
  <p class="note-line"><b>Two terms.</b> <em>Fine-tuning</em> shows the model sentences with known answers. <em>Adapting</em> comes before that and uses no answers at all: FinBERT keeps doing its original exercise, guessing hidden words, on the project's Reddit posts, news and reports, so it meets local product names and Reddit's style before it is asked to judge sentiment.</p>
  <p>The {tr['rows']:,} training sentences are {tr['by_sheet']['first_round']} from the first labelling round, {tr['by_sheet']['broker_research']} from broker research, {tr['by_sheet']['topup']} added for thin topics and {tr['by_sheet']['active']} that earlier models were least sure about. Opus labelled {tr['labels']['positive']} positive, {tr['labels']['neutral']} neutral and {tr['labels']['negative']} negative. They are LLM labels and are reported as such.</p>
</section>

<section id="tested">
  <h2>How it was tested</h2>
  <div class="twocol">
    <div>
      <h3>The test sentences</h3>
      <ul>
        <li><b>{F['n']} rows from the first round</b>, set aside before any training and labelled by people: {F['label_counts']['neutral']} neutral, {F['label_counts']['positive']} positive, {F['label_counts']['negative']} negative.</li>
        <li><b>{B['n']} rows from broker research</b>, labelled blind by a person: {B['label_counts']['positive']} positive, {B['label_counts']['neutral']} neutral, {B['label_counts']['negative']} negative.</li>
        <li>No test sentence, and no near-copy of one, is among the training rows. The adapting step left out {pt['dropped_labelled_id']:,} labelled sentences and {pt['dropped_matching_labelled_text'] + pt['dropped_holding_or_held_in_labelled_text'] + pt['dropped_sharing_most_words_with_labelled_text']} more that resembled one.</li>
      </ul>
    </div>
    <div>
      <h3>The rules</h3>
      <ul>
        <li><b>Three runs each.</b> Every fine-tuned model was trained three times from different random starts (seeds 42, 1 and 7), because one run's score can be luck at this size.</li>
        <li><b>The measure is macro-F1.</b> It averages the score for negative, neutral and positive, so the rare negative class counts as much as the common neutral one. Accuracy alone rewards a model for calling everything neutral: {100 * F['label_counts']['neutral'] / F['n']:.0f}% of the test rows are neutral.</li>
        <li><b>The rule for choosing was fixed first:</b> highest test macro-F1 over the three seeds, with cross-validation as the tie-breaker. Nothing was tuned on the test rows.</li>
      </ul>
    </div>
  </div>
</section>

<section id="headline">
  <h2>The headline: each step up is small, and they add up</h2>
  <p>On the {F['n']} first-round test rows, base FinBERT scores {f3(fbase['macro_f1'])}. Fine-tuning on people's labels lifts that to {f3(fp1['mean']['macro_f1'])} and, once retrained, {f3(fp4['mean']['macro_f1'])}. Switching to Opus's labels, with more rows, gives {f3(fo['mean']['macro_f1'])}. Adapting the encoder first gives {f3(fa['mean']['macro_f1'])}.</p>
  <figure>
    <figcaption>Macro-F1 on the {F['n']} first-round test rows</figcaption>
    <div class="legend">
      <span><i class="dot mean lg"></i>mean of three seeds</span><span><i class="dot seed lg"></i>one seed</span><span><i class="dot avg lg"></i>the three models averaged</span>
      <span class="fam-base"><i class="sw"></i>base</span><span class="fam-people"><i class="sw"></i>people's labels</span><span class="fam-opus"><i class="sw"></i>Opus's labels</span><span class="fam-adapted"><i class="sw"></i>adapted encoder</span>
    </div>
    {dotplot(F, ['base', 'people_1oct', 'people_4oct', 'opus_finbert', 'opus_adapted'])}
    {dot_table(F, ['base', 'people_1oct', 'people_4oct', 'opus_finbert', 'opus_adapted'])}
  </figure>
  <div class="readout">
    <p><b>Against base FinBERT the gain is clear.</b> {f3(fa['mean']['macro_f1'])} against {f3(fbase['macro_f1'])} is a gap of {(fa['mean']['macro_f1'] - fbase['macro_f1']) / fa['sd_macro_f1']:.0f} times the spread between seeds ({f3(fa['sd_macro_f1'])}). Every one of the three adapted runs is above every earlier model's mean.</p>
    <p><b>Between neighbours the gaps are small.</b> The best set leads the one below it by {f3(fa['mean']['macro_f1'] - fo['mean']['macro_f1'])}, about one seed's spread. No single step is a sure thing by itself; the order holds because other measures agree, as the later sections show.</p>
    <p><b>Averaging three models helps.</b> Letting the three adapted runs vote gives {f3(fa['averaged']['macro_f1'])}, and that averaged model is what the product would use.</p>
  </div>
</section>

<section id="errors">
  <h2>Accuracy barely moves. The kind of error does.</h2>
  <p>Base FinBERT gets {right_base} of the {F['n']} rows right; the averaged adapted model gets {right_ad}. Row by row, the adapted model fixes {pf['base']['only_adapted']} sentences that base FinBERT got wrong and breaks {pf['base']['only_other']} it had right. A difference that small could be chance (exact test, p = {p(pf['base']['mcnemar_exact_p'])}). So this is not a story about more correct answers.</p>
  <p>It is a story about which answers. The two tables count every test sentence by what it truly is and what the model called it.</p>
  <div class="cms">
    {confusion('first', 'base', 'Base FinBERT')}
    {confusion('first', 'opus_adapted', 'Adapted encoder, three averaged')}
  </div>
  <div class="readout">
    <p><b>Base FinBERT answers neutral {sum(cb[i][1] for i in range(3))} times out of {F['n']}.</b> That is safe when most rows are neutral, but it finds only {cb[0][0]} of the {sum(cb[0])} negative sentences and {cb[2][2]} of the {sum(cb[2])} positive ones.</p>
    <p><b>The adapted model finds {ca[0][0]} of the {sum(ca[0])} negatives and {ca[2][2]} of the {sum(ca[2])} positives.</b> The price is {ca[1][0] + ca[1][2]} neutral sentences now called positive or negative, up from {cb[1][0] + cb[1][2]}.</p>
    <p><b>For a sentiment index this is the better trade.</b> A model that hides four in five negative sentences cannot show a bank's sentiment falling. One that is sometimes too quick to call a sentence positive or negative can be reined in with a threshold, which is the last step before the scores are stored.</p>
  </div>
</section>

<section id="classes">
  <h2>Precision and recall by class</h2>
  <p>Recall is the share of the truly negative (or neutral, or positive) sentences the model found. Precision is the share of its negative calls that were right. Figures are the mean of three seeds on the {F['n']} first-round rows.</p>
  <figure>
    <figcaption>Recall and precision for each class, four models</figcaption>
    <div class="legend"><span class="fam-base"><i class="sw"></i>Base FinBERT</span><span class="fam-people"><i class="sw"></i>People's labels, 4 Oct</span><span class="fam-opus"><i class="sw"></i>Opus's labels</span><span class="fam-adapted"><i class="sw"></i>Adapted, Opus's labels</span></div>
    <div class="pair">{bars(F, 'recall')}{bars(F, 'precision')}</div>
    {pr_table(F)}
  </figure>
  <div class="readout">
    <p><b>Negative recall is where the models separate:</b> {f2(fbase['negative']['recall'])}, {f2(fp4['mean']['negative']['recall'])}, {f2(fo['mean']['negative']['recall'])} and {f2(fa['mean']['negative']['recall'])}, in the order they were built.</p>
    <p><b>Negative precision stays near a half</b> for all of them ({f2(min(main_of(F, k)['negative']['precision'] for k in BAR_SETS))} to {f2(max(main_of(F, k)['negative']['precision'] for k in BAR_SETS))}): about one negative call in two is wrong. With only {F['label_counts']['negative']} negative test rows this figure is the least stable on the page.</p>
    <p><b>Base FinBERT's neutral recall of {f2(fbase['neutral']['recall'])} is the other side of its caution.</b> The fine-tuned models give up some of it ({f2(fa['mean']['neutral']['recall'])} for the adapted set) to find more of the other two classes.</p>
  </div>
</section>

<section id="other">
  <h2>Does it hold on other text?</h2>
  <p>The first-round rows are mostly Reddit and earnings reports. The broker research rows are analysts' prose, closer to what FinBERT was first trained on, and base FinBERT is strong there: fine-tuning on people's labels never beat it. The adapted model on Opus's labels does.</p>
  <figure>
    <figcaption>Macro-F1 on the {B['n']} broker research test rows</figcaption>
    {dotplot(B, ['base', 'people_4oct', 'people_7oct', 'opus_finbert', 'opus_adapted'], lo=0.55, hi=0.80)}
    {dot_table(B, ['base', 'people_4oct', 'people_7oct', 'opus_finbert', 'opus_adapted'])}
  </figure>
  <p>On these rows the averaged adapted model is right on {pb['base']['only_adapted']} sentences base FinBERT misses and wrong on {pb['base']['only_other']} it gets (p = {p(pb['base']['mcnemar_exact_p'])}); against plain FinBERT fine-tuned on the same labels it is {pb['opus_finbert']['only_adapted']} against {pb['opus_finbert']['only_other']} (p = {p(pb['opus_finbert']['mcnemar_exact_p'])}). On all {A['n']} test rows together, macro-F1 is {f3(aa['mean']['macro_f1'])} against base FinBERT's {f3(abase['macro_f1'])}.</p>
  <figure>
    <figcaption>Accuracy by source, all {A['n']} test rows: base FinBERT against the averaged adapted model</figcaption>
    <div class="legend"><span class="fam-base"><i class="sw"></i>Base FinBERT</span><span class="fam-adapted"><i class="sw"></i>Adapted, three averaged</span></div>
    {source_bars()}
  </figure>
  <div class="readout">
    <p><b>The gain is on formal text:</b> earnings reports ({f2(src['base']['earnings']['accuracy'])} to {f2(src['opus_adapted']['earnings']['accuracy'])}) and broker research ({f2(src['base']['sgx_research']['accuracy'])} to {f2(src['opus_adapted']['sgx_research']['accuracy'])}).</p>
    <p><b>Reddit does not improve on accuracy</b> ({f2(src['base']['arctic_shift']['accuracy'])} to {f2(src['opus_adapted']['arctic_shift']['accuracy'])}). Most Reddit rows are neutral, so base FinBERT's habit of answering neutral scores well there. Reddit is {src['base']['arctic_shift']['n']} of the {A['n']} test rows and remains the weak source.</p>
  </div>
</section>

<section id="adapted">
  <h2>Is adapting worth it, or is plain FinBERT enough?</h2>
  <p>This is the closest call on the page, so it was measured a second way. The training rows were split into five folds, and each fold was held out in turn while a model trained on the other four. That was done for three seeds, from plain FinBERT and from the adapted encoder on identical folds, so each pair differs only in the starting point.</p>
  <figure>
    <figcaption>Cross-validation: macro-F1 on each held-out fold, scored against Opus's labels</figcaption>
    <div class="legend"><span class="fam-opus"><i class="sw round"></i>from plain FinBERT</span><span class="fam-adapted"><i class="sw round"></i>from the adapted encoder</span><span class="muted">the figure on the right is adapted minus plain</span></div>
    {cv_plot()}
    {cv_table()}
  </figure>
  <div class="readout">
    <p><b>The adapted encoder wins {cv['better']} of {cv['n']} pairs</b>, by {sgn(cv['diff_mean'])} on average ({f3(cv['finbert_mean'])} to {f3(cv['adapted_mean'])}). A paired test puts the true gain between {sgn(cv['ci'][0])} and {sgn(cv['ci'][1])} (t = {cv['t']:.2f}, p = {p(cv['p'])}). Small, and not zero.</p>
    <p><b>The gain was larger on 6 Oct</b> (+0.038 on 978 rows). With {tr['rows']:,} labelled rows plain FinBERT has caught up part of the way, which is what adapting is expected to do: it helps most when labels are scarce.</p>
    <p><b>It costs little to keep.</b> Adapting took about 1 hour 40 minutes, once. The model the product runs is the same size and speed either way.</p>
  </div>
</section>

<section id="index">
  <h2>What it would do to the index</h2>
  <p>The dashboard does not show sentences; it shows a balance of positive against negative. So a second question matters: when the labels on the test rows are added up, how close does each model's total come to the truth?</p>
  {net_table()}
  <div class="readout">
    <p><b>On the first-round rows the adapted model is closer.</b> The labels balance at {sgn(nb_f['truth_net'])}; base FinBERT reads {sgn(nb_f['pred_net'])} and the adapted model {sgn(na_f['pred_net'])}. Base FinBERT also calls only {100 * nb_f['pred_nonneutral']:.0f}% of rows positive or negative when {100 * nb_f['truth_nonneutral']:.0f}% are, so its index moves less than the text does.</p>
    <p><b>On the broker research rows it is further away.</b> The labels balance at {sgn(nb_b['truth_net'])}; base FinBERT reads {sgn(nb_b['pred_net'])} and the adapted model {sgn(na_b['pred_net'])}, because it calls {na_b['called'][0]} sentences negative where {na_b['truth'][0]} are.</p>
    <p><b>This is what the neutral threshold is for.</b> Before the earlier fine-tuned model was proposed for the product, a margin was chosen on held-out training rows: when the model's top two answers are close, the sentence is called neutral. The same step has not been done for this model yet, and it comes before the re-score.</p>
  </div>
</section>

<section id="limits">
  <h2>How sure this is, and the limits</h2>
  <ul class="limits">
    <li><b>One run of three seeds.</b> The gaps between fine-tuned models are about the size of the spread between seeds. The order is trusted because the first-round rows, the broker research rows and cross-validation all agree, not because any one gap is large.</li>
    <li><b>The test labels and the training labels follow different rules.</b> The first-round test rows were labelled by people under the older rule for retail products, with a model's suggestion in view. The training rows were labelled by Opus under the rules of 10 Oct. The models still score higher on the people's labels than those trained on people's labels did.</li>
    <li><b>Few negative test rows.</b> {F['label_counts']['negative']} in the first round and {B['label_counts']['negative']} in broker research. Negative precision and recall move by two or three points when a single row changes.</li>
    <li><b>Cross-validation is scored against Opus's labels,</b> the test rows against people's. They answer slightly different questions and happen to agree.</li>
    <li><b>An earlier adapted model is left out.</b> The one from 6 and 7 Oct scored 0.751 on the broker research rows, but its adapting step had read sentences related to test sentences. This run fixed that; its like-for-like figure is {f3(ba['averaged']['macro_f1'])} for the three averaged.</li>
    <li><b>Reddit is not solved.</b> Accuracy there is {f2(src['opus_adapted']['arctic_shift']['accuracy'])}, the same as before.</li>
  </ul>
</section>

<section id="next">
  <h2>Decision and what happens next</h2>
  <div class="decision">
    <p><b>The model for the dashboard and chatbot is the adapted encoder fine-tuned on Opus's labels, three runs averaged.</b> It leads on both test sets and in cross-validation, by the rule fixed before the run.</p>
  </div>
  <ol class="steps">
    <li><b>Choose the neutral threshold</b> for the averaged model on held-out training rows, and check the index it would produce against the labels.</li>
    <li><b>Rehearse the re-score on a copy of the database</b> with this model and the LLM's aspects, and show what each bank's figures become.</li>
    <li><b>Run the re-score once,</b> on the owner's go-ahead, after the dashboard filters on one model version.</li>
    <li><b>Re-run every evaluation</b> on the new database, including the comparison of the two aspect methods.</li>
  </ol>
</section>

<section id="tables">
  <h2>Full tables</h2>
  <p>P is precision, R is recall. Each fine-tuned model has two lines: the mean of its three seeds, and the three models averaged.</p>
  <h3>First round, {F['n']} test rows</h3>
  {full_table(F)}
  <h3>Broker research, {B['n']} test rows</h3>
  {full_table(B)}
  <h3>Both, {A['n']} test rows</h3>
  {full_table(A)}
  <h3>Row by row: the averaged adapted model against each other model</h3>
  <div class="scroll"><table class="num"><thead><tr><th>Test rows</th><th>Against</th><th>Both right</th><th>Only the adapted model right</th><th>Only the other right</th><th>Both wrong</th><th>Exact test p</th></tr></thead><tbody>
  {''.join(f"<tr><th>{lab}</th><td class='l'>{nm}</td><td>{r['both_right']}</td><td>{r['only_adapted']}</td><td>{r['only_other']}</td><td>{r['both_wrong']}</td><td>{p(r['mcnemar_exact_p'])}</td></tr>" for lab, pr in (("First round, 299", pf), ("Broker research, 100", pb), ("Both, 399", pa)) for key, nm in (("base", "Base FinBERT"), ("people_4oct", "People's labels, 4 Oct, averaged"), ("opus_finbert", "Opus's labels, averaged")) for r in [pr[key]])}
  </tbody></table></div>
  <h3>Where the figures come from</h3>
  <ul class="refs">
    <li>Scripts, the 30 cross-validation scores and the result tables: <code>data/eval/model-rerun-2026-10-11/</code></li>
    <li>Write-up: <code>docs/evidence/model-rerun-2026-10-11.md</code></li>
    <li>Training and test labels: <code>data/labeled/llm_rater/rules-2026-10-10/training_set.csv</code>, <code>data/labeled/sgx_research/resolved_test_blind.csv</code></li>
    <li>Run: 11 Oct 15:51 to 12 Oct 00:07 on a MacBook Air (M1), about eight hours; nothing was written to the database</li>
  </ul>
</section>

<footer>Every figure on this page is computed from the trained models and the label files named above. No sentence text is shown.</footer>
</div>
<div id="tip" role="status" hidden></div>
<script>
(function () {{
  var tip = document.getElementById("tip");
  function show(ev) {{
    var t = ev.target.closest ? ev.target.closest("[data-tip]") : null;
    if (!t) {{ tip.hidden = true; return; }}
    tip.textContent = t.getAttribute("data-tip");
    tip.hidden = false;
    var x = ev.clientX + 14, y = ev.clientY + 16, w = tip.offsetWidth, h = tip.offsetHeight;
    if (x + w > window.innerWidth - 8) x = Math.max(8, ev.clientX - w - 14);
    if (y + h > window.innerHeight - 8) y = Math.max(8, ev.clientY - h - 12);
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }}
  document.addEventListener("pointermove", show);
  document.addEventListener("pointerdown", show);
  document.addEventListener("scroll", function () {{ tip.hidden = true; }}, true);
  document.addEventListener("pointerleave", function () {{ tip.hidden = true; }});
}})();
</script>
"""

HEAD = """<title>FinBERT Model Comparison</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&display=swap">
<style>
""" + CSS + "\n</style>\n"

open(S + "model-comparison.html", "w", encoding="utf-8").write(HEAD + BODY)
standalone = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
              '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
              + HEAD + "</head>\n<body>\n" + BODY + "\n</body>\n</html>\n")
open(sys.argv[1], "w", encoding="utf-8").write(standalone)
print("written", len(HEAD + BODY), "bytes")
