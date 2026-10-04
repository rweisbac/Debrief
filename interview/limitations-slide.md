# What Debrief does not do yet

- **No real systems or users.** Gong, Salesforce and Slack are file-backed mocks, and no seller has used it. [repo] `src/adapters.py`, `README.md` "Production path"
- **No independent ground truth.** All 27 transcripts and their gold labels were written by the builder, on synthetic data only. [repo] `README.md` "Known limits", `eval/gold_src.py`
- **No variance estimate.** Every recorded result is 1 run per deal, and the judges are uncalibrated model calls. [repo] DECISIONS D-15, `evals/judges.py`, `eval/score.py`
- **No recorded output for 2 built features.** The post-call confirm card and the best practice profile have code and tests, with no live recording yet. [repo] DECISIONS D-16, D-17
- **No log redaction in practice.** Redaction runs only when presidio is installed, and it is not. [repo] DECISIONS D-04, `src/llm.py`
