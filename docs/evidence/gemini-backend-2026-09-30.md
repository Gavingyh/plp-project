# Gemini backend: first live test

The Gemini backend (`chatbot/backends/gemini_backend.py`) was written to
Google's documented REST contract and had never received a real response.
Tested on 2026-09-30 with the team's free-tier key.

## Keeping within the free-tier terms

Google's Gemini API Additional Terms (updated 2026-04-28) let Google use
free-tier prompts and responses to improve its products, with human review,
and say not to submit sensitive, confidential or personal information. So
the test offered the model every tool except `search_evidence`, the only one
that returns corpus text (Reddit posts, article sentences). What reached
Google: the system prompt, the tool schemas, the questions, and index
figures. The team's key is for the chatbot only.

## Models

The key's model list (`GET /v1beta/models`) included `gemini-3.8-flash`,
`gemini-3.7-flash` and `gemini-3.6-flash`. At the time of testing:

| model | result |
|---|---|
| `gemini-3.8-flash` (the configured model) | HTTP 503, "currently experiencing high demand", repeatedly |
| `gemini-3.7-flash` | HTTP 503, the same |
| `gemini-3.6-flash` | answered in about 2 s, with occasional 503s |
| `gemini-2.5-flash` | HTTP 404, "no longer available to new users" |

## Result

Run through the full chatbot turn (`chatbot.agent.answer_turn`: guards, tool
loop, figure and citation checks) on `gemini-3.6-flash`:

| question | tool calls | checks | outcome |
|---|---|---|---|
| What is the overall sentiment for DBS right now? | `get_sentiment(DBS)`, `get_trend(DBS)` | no flags | correct: +0.122 on 24,431 sentences, the stored index value |
| Compare DBS, OCBC and UOB on dividend policy. | `compare_banks(dividend_policy)`, `get_trend` for each bank | no flags | correct: OCBC +0.208, DBS +0.199, UOB +0.124, the stored values |
| Should I buy DBS shares? | none | answered by the advice guard | the model was not called |

So the function-declaration conversion (uppercase schema types) and the
`functionResponse` continuation work as written. Two changes came out of
the test:

- The backend now retries a 503 or 429 up to three times (2, 5 and 15 s).
  The first question failed on a single 503 before this; after it, two 503s
  were absorbed.
- The advice and out-of-scope replies listed the four old aspects; they now
  describe the ten.

Not tested: `search_evidence` through Gemini (it would send corpus text), a
multi-turn conversation, and the gold-set evaluation. A Gemini key from AI
Studio need not start with `AIza`: this one didn't, and works.
