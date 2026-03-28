.PHONY: report test dashboard-ingest dashboard-doctor dashboard-generate dashboard-serve

report:
	python3 codex_usage_report.py

test:
	python3 -m unittest discover -s tests -v

dashboard-ingest:
	python3 -m dashboard.cli ingest

dashboard-doctor:
	python3 -m dashboard.cli doctor

dashboard-generate:
	python3 -m dashboard.cli generate --latest

dashboard-serve:
	python3 -m dashboard.cli serve
