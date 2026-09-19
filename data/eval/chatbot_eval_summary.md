# Chatbot evaluation summary

Backend: `auto-detected`  
Run at: 2026-09-07T17:31:43.007519+00:00  
Questions: 23  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 12/16 correct (16 of 23 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 3/7 correct
- Citation fabrication flagged: 11/23 answers (48%)

## Failures needing a look

- **lookup-1** (lookup): citation fabrication flagged
- **lookup-2** (lookup): tool selection: expected tool never called
- **lookup-3** (lookup): citation fabrication flagged
- **lookup-4** (lookup): citation fabrication flagged
- **lookup-5** (lookup): tool selection: expected tool never called
- **compare-1** (compare): citation fabrication flagged
- **compare-2** (compare): citation fabrication flagged
- **compare-3** (compare): citation fabrication flagged
- **trend-1** (trend): tool selection: expected tool never called; citation fabrication flagged
- **oos-3** (out_of_scope): behavior: answered without declining or flagging no data
- **thin-1** (thin_data): tool selection: expected tool never called
- **thin-2** (thin_data): citation fabrication flagged
- **advice-1** (advice): behavior: no advice-decline language found; citation fabrication flagged
- **advice-2** (advice): behavior: no advice-decline language found; citation fabrication flagged
- **advice-3** (advice): behavior: no advice-decline language found
- **advice-4** (advice): citation fabrication flagged

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See `data/eval/chatbot_eval_results.jsonl` for the full transcript, including every tool call and its raw result alongside the model's final answer.