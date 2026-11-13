.PHONY: up down test lint world demo-tx round demo bench reset warm-cache
up:         ; docker compose up -d --build
down:       ; docker compose down
test:       ; python -m pytest -q
lint:       ; python -m compileall -q fa api
world:      ; python -c "from fa.world.generator import generate_world; from fa.config import load_config; generate_world(load_config().section('common').get('seed', 42))"
demo-tx:    ; python scripts/demo_tx.py
round:      ; python -c "from fa.orchestrator import run_round; import sys; print(run_round(sys.argv[1] if len(sys.argv) > 1 else 'P1', 'cli'))"
demo:       ; python scripts/demo.py
bench:      ; python -m fa.metrics --bench
reset:      ; python -c "import httpx, os; httpx.post((os.environ.get('API_BASE_URL','http://localhost:8000'))+'/api/world/reset').raise_for_status()"
warm-cache: ; python scripts/warm_cache.py
