.PHONY: test smoke style record eval ablation candidates demo

test:
	python -m pytest -q

smoke:
	python scripts/smoke_test.py

style:
	python scripts/check_style.py

# Calls the API (needs ANTHROPIC_API_KEY) and saves replay fixtures for all 5 deals, including judge calls.
record:
	DEBRIEF_MODE=record python evals/run_evals.py --mode record --runs 1
	DEBRIEF_MODE=record python evals/verifier_ablation.py --mode record

# Offline: scores from replay fixtures only. Missing fixtures are reported, never fetched.
eval:
	DEBRIEF_MODE=replay python evals/run_evals.py --mode replay
	DEBRIEF_MODE=replay python evals/verifier_ablation.py --mode replay

ablation:
	python evals/verifier_ablation.py

candidates:
	python evals/make_candidates.py

# demo target arrives in checkpoint 3.
