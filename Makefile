.PHONY: report test

report:
	python3 codex_usage_report.py

test:
	python3 -m unittest discover -s tests -v
