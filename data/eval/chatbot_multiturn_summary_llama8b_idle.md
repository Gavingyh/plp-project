# Multi-turn evaluation

Model: `OllamaBackend / llama3.1:8b`  
Turns correct: 7/9; conversations with every turn correct: 2/4

| scenario | turn | question | correct | reason |
|---|---|---|---|---|
| mt-1 | 1 | What is the sentiment on DBS's dividend policy? | True |  |
| mt-1 | 2 | And OCBC? | True |  |
| mt-2 | 1 | How is UOB doing overall? | True |  |
| mt-2 | 2 | What about its asset quality? | True |  |
| mt-2 | 3 | Has that improved lately? | False | expected tool never called |
| mt-3 | 1 | Compare the three banks on net interest margin. | True |  |
| mt-3 | 2 | Show me some evidence for DBS on that. | False | expected tool never called |
| mt-4 | 1 | What do analysts think of OCBC? | True |  |
| mt-4 | 2 | So should I buy it? | True |  |
