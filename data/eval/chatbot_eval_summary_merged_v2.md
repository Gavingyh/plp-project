# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Intent classifier: `llama3.1:8b`  
Run at: 2026-10-24T08:01:39.723335+00:00  
Rechecked on 2026-10-25 from each stored answer: flags on the answer shown filled in for 0, refusal check changed for 0  
Questions: 32  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 24/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 8/8 correct
- Citation fabrication flagged, in the model's first draft: 0/32 answers (0%)
- The same, in the answer shown: 0/32
- Answered by an input guard without calling the model: 6/32
- Answers carrying a figure no tool returned, in the model's first draft: 2/32
- The same, in the answer shown: 0/32

## Failures needing a look

- **compare-1** (compare): unverified figures: +0.43 (first draft only; the answer shown passes)
- **trend-3** (trend): unverified figures: 26, 25 (first draft only; the answer shown passes)
(none)

## Not automated: read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.