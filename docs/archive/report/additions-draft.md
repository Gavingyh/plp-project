# Report additions: draft text for the seven new analyses

Every number below is a placeholder written as `<...>`. Fill each from the command shown,
run on the SUBMITTED database and model version. Smoke-test numbers from earlier databases
must not be used.

## A. Checking the index against outside evidence (Findings)
Command: `python -m aggregate.price_check --fetch` after putting real results-release dates
in `data/prices/earnings_dates.csv`.
Text: "We compared the monthly index with the next month's share-price return for each bank
(Spearman rank correlation, 95% bootstrap interval, permutation p-value) and with the
reaction around results releases. The correlation was <rho> (<lo> to <hi>, n = <months>
months, p = <p>). With this many months, only a correlation larger than about <x> could be
told from chance, so a weak result is not evidence of no relationship." State plainly if the
interval includes zero. Do not claim the index predicts prices unless the interval excludes zero
at every lag tested, and say how many lags were tried.

## B. How sure the index is (Findings, Limitations)
Command: `python -m aggregate.uncertainty --bootstrap 2000 --unit document` and `--unit sentence`.
Text: "Resampling whole documents (a Reddit thread or a results report is one unit), the index
for DBS is <s> (95% interval <lo> to <hi>); OCBC <..>; UOB <..>. The gap between DBS and
OCBC is <d> (<lo> to <hi>)." If an interval for a gap includes zero, the ranking of those two
banks is not supported and the text must say so. Explain why document resampling is wider
than sentence resampling (sentences in one document are not independent).

## C. Topic modelling as a check on the ten topics (Method, Results)
Command: `python -m aspects.topic_model --k 11 --methods nmf lda`.
Text: "We fitted NMF and LDA with k = <k> and compared the topics with the human aspect
labels. NMI = <nmi> against a shuffled-label chance level of <chance>; purity <p>; mean NPMI
coherence <c>. Topics that matched a single aspect: <list>. Topics that mixed aspects: <list>."
Say that topic models find word co-occurrence, not our definitions, so partial agreement is
expected; use it to find sentences where the ten-topic list may be missing a theme.

## D. Word analysis (Findings)
Command: `python -m scripts.term_analysis --charts`.
Text: "Using weighted log-odds with an informative prior (Monroe et al.), words most
distinctive of Reddit were <list> and of earnings reports <list>. Words most distinctive of
negative sentences were <list>." Mention that rare words are excluded (min count <n>).

## E. Aspect and opinion-term extraction (Method, Results)
Commands: `python -m aspects.extract_terms --sample 300 --export-gold data/eval/terms/gold_sheet.csv`,
two people annotate, then `--evaluate <filled sheet>`.
Text: "A local model extracted aspect-term/opinion-term pairs; any span not found in the
sentence was dropped (<x>% of pairs). Against <n> sentences annotated by <people>, exact-match
F1 was <f1> and relaxed-match F1 <f1r> (precision <p>, recall <r>)." Report annotator agreement
on a double-annotated subset. No accuracy claim without the filled sheet.

## F. Opinion summarisation (Method, Results)
Command: `python -m chatbot.summarise --all-aspects`; then people fill
`data/eval/summaries/rating_sheet.csv`.
Text: "For each bank and topic the system gives up to three praised and three criticised points,
each citing the sentences behind it. Automatic checks dropped <x> of <y> points. On <n> points
rated by <people>, <p>% were supported by their cited sentences (0/1) and usefulness averaged
<u> out of 5." Limitation: a point can be supported yet unrepresentative; retrieval picks the
highest-ranked sentences, not a random sample.

## G. Second neural network and classical baselines (Method, Results)
Commands: `python -m train.baselines_classical`; `python -m train.bilstm_baseline --arch bilstm`
and `--arch cnn` (add `--glove <file>` for GloVe).
Text: "On the same <n_train> training and <n_test> test sentences, Naive Bayes scored <f1>,
a linear SVM <f1>, logistic regression <f1>, a BiLSTM <f1 +/- sd over 3 seeds> and the
fine-tuned FinBERT <f1 +/- sd>. The paired bootstrap difference between FinBERT and the best
baseline was <d> (<lo> to <hi>)." Use `train.baselines_classical.paired_bootstrap` on the saved
test predictions. If the interval includes zero, do not say FinBERT is better.

## H. Conversation design (Conversational UI)
See `docs/report/conversation-design.md`. Replace the placeholder dialogues with real
transcripts, and report the scripted-dialogue check from its section 8.
