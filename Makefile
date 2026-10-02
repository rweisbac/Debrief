.PHONY: test smoke style record eval ablation candidates demo samples

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

# Offline demo: replay mode plus hand-written sample cards (labeled in the app). Never calls the API.
demo:
	DEBRIEF_MODE=replay DEBRIEF_SAMPLES=1 streamlit run app.py --server.headless true

# Rebuild the hand-written sample cards (fixtures/samples) through the real rules and checks.
samples:
	python scripts/build_samples.py
