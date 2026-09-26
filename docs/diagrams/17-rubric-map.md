# What each rubric item rests on

Each rubric item, the component that answers it, and the course module that component draws on, from `docs/PLAN.md` section 3. For the report's solution-approach section.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
flowchart LR
  accTitle: Rubric items, components and course modules
  accDescr: Nine rubric items each map to one component. Components draw on Text Analytics, New Media and Sentiment Mining, Text Processing using Machine Learning, and Conversational UIs. Bank entity recognition, LLM aspect categorisation and annotation are planned; the fine-tuned sentiment model is built but has never run.

  subgraph R["Rubric item"]
    r1["data"]
    r2["preprocessing"]
    r3["text-mining task 1"]
    r4["text-mining task 2"]
    r5["text-mining task 3"]
    r6["the DNN, text-mining task 4"]
    r7["labels"]
    r8["sentiment mining"]
    r9["conversational UI"]
  end

  subgraph C["Component, and the course modules it draws on"]
    c1["Corpus: Reddit, earnings,<br/>news, analyst consensus<br/><i>TA · NMSM</i>"]
    c2["Sentence segmentation,<br/>bank attribution<br/><i>TA</i>"]
    c3["Aspect discovery<br/>UMAP + HDBSCAN<br/><i>TA · NMSM</i>"]
    c4["Aspect categorisation<br/>by a local LLM<br/><i>TA · NMSM</i>"]
    c5["Bank entity recognition<br/>and resolution<br/><i>TA · NMSM</i>"]
    c6["Sentiment: fine-tuned FinBERT,<br/>built, never run<br/><i>TPML · NMSM</i>"]
    c7["Annotation, kappa at least 0.6<br/><i>TA</i>"]
    c8["Sentiment index, dashboard<br/><i>NMSM</i>"]
    c9["Chatbot with tool calling<br/><i>CNI</i>"]
  end

  key["<b>Course modules</b><br/>TA: Text Analytics<br/>NMSM: New Media and Sentiment Mining<br/>TPML: Text Processing using Machine Learning<br/>CNI: Conversational UIs"]

  r1 --> c1
  r2 --> c2
  r3 --> c3
  r4 -.-> c4
  r5 -.-> c5
  r6 --> c6
  r7 -.-> c7
  r8 --> c8
  r9 --> c9
  C ~~~ key

  classDef planned stroke-dasharray: 5 5,color:#555,fill:#fafafa;
  class c4,c5,c7 planned;
```

Rendered for the report: [SVG](img/17-rubric-map.svg) · [PNG](img/17-rubric-map.png)

## What this shows and doesn't show

One rubric item maps to one component. The modules each component draws on are
written inside it rather than drawn as arrows, because fourteen crossing arrows into four
boxes were unreadable. Three components are planned (dashed): the LLM aspect classifier,
bank entity recognition and the annotation round. The fine-tuned sentiment model is
written but has never run, because nothing is labelled yet; base FinBERT zero-shot scores
the corpus today. Aspect discovery is built and was run once to derive the taxonomy; PLAN
section 5 schedules a re-run. Not shown: the day-level course references and the
evaluation for each component, which are in the PLAN table this is drawn from.

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| data: corpus | `docs/PLAN.md:62` | `| Corpus: Reddit, earnings PDFs, news, analyst consensus | data |` |
| preprocessing | `docs/PLAN.md:63` | `| Sentence segmentation, bank attribution | preprocessing |` |
| task 3: bank NER | `docs/PLAN.md:64` | `| **Bank entity recognition and resolution** | text-mining task 3 |` |
| task 1: aspect discovery | `docs/PLAN.md:65` | `| **Aspect discovery** (FinBERT embeddings → UMAP → HDBSCAN) | text-mining task 1 |` |
| task 2: aspect categorisation | `docs/PLAN.md:66` | `| **Aspect categorisation** (local LLM, fixed schema) | text-mining task 2 |` |
| DNN, task 4: sentiment | `docs/PLAN.md:67` | `| **Sentiment classification** (fine-tuned FinBERT) | the DNN; text-mining task 4 |` |
| labels: annotation | `docs/PLAN.md:68` | `| Annotation | labels |` |
| sentiment mining: index, dashboard | `docs/PLAN.md:69` | `| Sentiment index, dashboard | sentiment mining |` |
| conversational UI: chatbot | `docs/PLAN.md:70` | `| **Chatbot** (tool calling over the index and evidence) | conversational UI |` |
| module abbreviations | `docs/PLAN.md:72` | `Course modules: TA = Text Analytics, NMSM = New Media and Sentiment Mining,` |
| aspect discovery is built | `aspects/discover.py:49` | `def run(min_cluster_size: int = 10)` |
| segmentation is built | `preprocess/segment.py:35` | `def segment(text: str)` |
| fine-tuning is built | `train/finetune.py:94` | `def run(seed: int = 42` |
| base FinBERT scores today | `dashboard/app.py:134` | `applied zero-shot; the fine-tuned model does not exist yet` |

## Planned elements

| element | recorded in |
|---|---|
| Aspect categorisation by a local LLM | DESIGN.md decision 16; PLAN.md D1 |
| Bank entity recognition and resolution | DESIGN.md decision 18; PLAN.md D3, section 7 |
| Annotation of aspect and sentiment | DESIGN.md decision 17; PLAN.md D2, section 6 |
