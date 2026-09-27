UV = uv run --no-editable
.PHONY: install serve doctor baseline incident demo test lint verify
install:
	uv sync --locked --no-editable
serve:
	$(UV) observatory serve
doctor:
	$(UV) observatory doctor
baseline:
	$(UV) observatory run --scenario baseline
incident:
	$(UV) observatory run --scenario queue-pressure
demo:
	$(UV) python scripts/demo.py
test:
	$(UV) pytest -q
lint:
	$(UV) ruff check src tests scripts
	$(UV) ruff format --check src tests scripts
verify:
	$(UV) python scripts/verify_traces.py $(TRACE_ID)
