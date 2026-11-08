.PHONY: check lint test abnahme docker-build examples

check: lint test

lint:
	uv run ruff check src tests abnahme
	uv run ruff format --check src tests abnahme

test:
	uv run pytest -q

abnahme:           ## Live-Abnahmetest (DIP + Sprachmodell), Ergebnis unter examples/
	uv run python abnahme/abnahme.py

docker-build:
	docker build -t dip-fraktionen .

examples:          ## alle Beispielausgaben neu erzeugen (Live: DIP + Sprachmodell); examples/ wird nur ersetzt, wenn kein Schritt abbricht
	rm -rf .examples-neu && mkdir .examples-neu
	uv run dip-fraktionen report --wahlperiode 20 --ausgabe .examples-neu
	uv run dip-fraktionen report --wahlperiode 21 --ausgabe .examples-neu
	{ echo "# Chat-Beispiele ($$(date +%F), Modell $${LLM_MODEL:-openai/gpt-oss-20b})"; \
	  for q in "Wie ist die Fraktionsverteilung in der 20. Wahlperiode?" "Wer ist Friedrich Merz?"; do \
	  printf '\n## Frage: %s\n\n' "$$q"; uv run dip-fraktionen ask "$$q" || exit 1; \
	  done; } > .examples-neu/chat_beispiele.md
	uv run python abnahme/abnahme.py .examples-neu; test $$? -ne 2
	rm -rf examples && mv .examples-neu examples
