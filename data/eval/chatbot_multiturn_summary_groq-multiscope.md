# Multi-turn evaluation

Model: `OpenAIBackend / openai/gpt-oss-120b`  
Turns correct: 9/9; conversations with every turn correct: 3/3

| scenario | turn | question | correct | reason |
|---|---|---|---|---|
| mts-1 | 1 | What is the sentiment on DBS's dividend policy? | True |  |
| mts-1 | 2 | How is the weather today? | True |  |
| mts-1 | 3 | And OCBC? | True |  |
| mts-2 | 1 | hi | True |  |
| mts-2 | 2 | How is UOB doing overall? | True |  |
| mts-2 | 3 | thanks! | True |  |
| mts-3 | 1 | What's the sentiment on OCBC's asset quality? | True |  |
| mts-3 | 2 | you're useless | True |  |
| mts-3 | 3 | Show me the quotes behind it. | True |  |
