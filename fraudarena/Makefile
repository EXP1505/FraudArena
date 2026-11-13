.PHONY: up down test demo-tx lint
up:        ; docker compose up -d --build
down:      ; docker compose down
test:      ; python -m pytest -q tests
demo-tx:   ; python scripts/demo_tx.py   # M1 writes this by H3:45
lint:      ; python -m compileall -q fa api
