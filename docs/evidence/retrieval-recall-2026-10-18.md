# Evidence search: Hit@5 and Recall@5 on the submitted database (18 Oct 2026)

Run on the 14 Oct database (`plp-2026-10-14.db`, 45,844 sentences) with
`python -m chatbot.retrieval_eval_recall`: the same script as `chatbot.retrieval_eval`
plus recall@K (patch in `recall_patch.diff`). 28 queries, the 1,277 labelled sentences,
same random baseline. Per-query results: `retrieval_recall_per_query_2026-10-18.csv`.

Check against the 14 Oct note: for the stored-aspect filter, by the aspect's name,
hit@1 0.679, precision@5 0.664, MRR 0.810 and the random row (0.738, 0.738, 0.853) all
reproduce exactly, and so do the question-words row (0.500, 0.621, 0.698) and the
1 Oct unfiltered rows.

| Search (K = 5) | hit@1 | hit@5 | precision@5 | recall@5 | MRR |
|---|---|---|---|---|---|
| Submitted database, filter, by the aspect's name | 0.679 | 1.000 | 0.664 | 0.379 | 0.810 |
| the same, by the question's words | 0.500 | 1.000 | 0.621 | 0.370 | 0.698 |
| random order within the filter | 0.738 | 0.996 | 0.738 | 0.399 | 0.853 |
| No filter, by the aspect's name (1 Oct figures reproduced) | 0.464 | 0.679 | 0.293 | 0.083 | 0.559 |
| random order, no filter | 0.098 | 0.319 | 0.098 | 0.015 | 0.217 |

Recall@10 with the filter, by the aspect's name: 0.563 (random 0.575).

## Reading it

- **Hit@5 is at its ceiling (1.000, random 0.996).** After the filter a bank's pool is
  mostly the right aspect, so any five sentences contain a relevant one. Hit@5 cannot
  tell a good ranking from a random one here.
- **Recall@5 is capped by the pool, not the ranking.** A query has 31 relevant
  sentences on average (median pool 20), so five results can recall at most 5/r:
  mean ceiling 0.51. The search reaches 0.379; a random five reaches 0.399.
- **The ranking is again no better than random.** Recall@5 is below random in 13 of the
  28 queries (by the aspect's name), and the largest shortfalls are in the big pools
  (DBS retail banking 0.011 against 0.022, management guidance 0.028 against 0.082).
  The same conclusion as precision@5 and MRR: the filter does the work, the ranking adds
  nothing.
- Hit@5 and recall@5 therefore complete the retriever metrics on the course slide
  (Hit Rate@K, Precision@K, Recall@K, MRR) and agree with the existing result.
