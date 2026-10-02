.PHONY: test smoke style

test:
	python -m pytest -q

smoke:
	python scripts/smoke_test.py

style:
	python scripts/check_style.py

# eval, demo and record targets arrive in checkpoints 2 and 3.
