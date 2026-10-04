# What Debrief does not do yet

- **No real systems or users.** Gong, Salesforce and Slack are file-backed mocks, and no seller has used it. [repo] `src/adapters.py`, `README.md` "Production path"
- **No independent ground truth.** All 27 transcripts and their gold labels were written by the builder, on synthetic data only. [repo] `README.md` "Known limits", `eval/gold_src.py`
- **No variance estimate.** Every recorded result is 1 run per deal, and the judges are uncalibrated model calls. [repo] DECISIONS D-15, `evals/judges.py`, `eval/score.py`
- **Brittle on short calls and too quick to block.** A word-count rule labeled 6 of 15 test calls low information when only 1 was, and 6 of 14 blocked drafts were false alarms. [eval] `eval/hand_review.md`
- **No log redaction in practice.** Redaction runs only when presidio is installed, and it is not. [repo] DECISIONS D-04, `src/llm.py`
