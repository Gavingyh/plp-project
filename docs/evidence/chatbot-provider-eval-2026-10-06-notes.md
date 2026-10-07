## Reading the answers (written 7 Oct 2026 from the transcripts)

These notes come from reading the saved answers in `data/eval/chatbot_eval_results_<arm>-<set>.jsonl`. They
are one person's reading of one run per model, so treat them as leads, not findings.

**Run status.** Ollama and Groq answered every question. Gemini was not run: the key in `.env` is rejected by
Google (HTTP 401), and it is 53 characters long without the `AIza` start that an AI Studio key has. Create a key at
aistudio.google.com/apikey, put it in `.env` as `GEMINI_API_KEY`, then run `python -m chatbot.provider_eval --arms gemini`.
Nothing about Gemini can be concluded from this report. No request hit a rate limit: Groq received 128 requests
for the evaluation (131 counting a 3-request check beforehand) against a budget of 700 in 24 hours, and no 429 was returned.

**The three questions where the arms differ**

- *oos-2 (HSBC), and oos-1 (Standard Chartered), mixed-1 (weather):* all three of Groq's missed decline checks are
  correct declines that the detector in `chatbot/eval_gold_set.py` did not recognise. oos-2: "I only have sentiment data for
  Singapore's three listed banks... I don't have market-feel information for HSBC". oos-1 is worded the same way. mixed-1:
  "I can't help with the weather", then the DBS answer. The detector looks for fixed phrases such as "don't have data" and
  "only cover", and Groq writes the apostrophe as a typographic one (don't). Normalising the apostrophe on the saved answers makes
  mixed-1 pass; oos-1 and oos-2 still miss because their wording is not in the phrase list. I have not changed the detector, because
  that would change a frozen check after seeing results; it is a decision for the team. Ollama passed oos-2 with "I have no data
  on HSBC." Ollama's two misses: oos-1 ("There isn't enough data to answer reliably.", a terse no-data reply the detector also
  missed) and mixed-1, where it answered the DBS part and said nothing about the weather, a real miss.
- *thin-1 and ctrl-4:* the local model (`llama3.1:8b`) did not call the tool. On thin-1 it gave a 7-day score for UOB with no
  tool call behind it; on ctrl-4 it wrote "I will call the get_sentiment tool" instead of calling it. Groq called the tool both times
  and answered with the returned figures. These are real differences in following the tool-use instructions, on two questions.

**Figures flagged as not returned by a tool.** Groq 5 answers, Ollama 2. The check is strict and a flagged figure still needs a
person to read it. In the Groq answers, several flagged values are small whole numbers or a thousands-separated number inside
a sentence the model composed (`24`, `11`, `10`, `49,700`), which may be counts or dates it restated rather than invented, and I did not
check each against its tool result. One Groq answer (trend-3) contains a stray tool tag, `functions.get_trend`, in the visible text,
which a user would notice.

**What this does and does not show.** On these 61 questions and 18 conversation turns, `gpt-oss-120b` on Groq used the right tool
on 27 of 27 checked questions against 25 of 27 for the local model, and both got 9 of 9 and 9 of 9 conversation turns right. The
decline-and-no-data check reads 7 of 9 for the local model and 6 of 9 for Groq, but on my reading of the answers all of
Groq's three misses are correct declines the detector did not recognise, so that figure understates Groq and the
detector, not the model, is the weak part. The hosted model never sees Reddit, CNA or broker-research text, so these tests (which mostly ask for scores and
trends) do not exercise the thing it cannot see. With this few questions and one run each, a gap of one or two is not a ranking.
