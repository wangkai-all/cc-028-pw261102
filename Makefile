.PHONY: install backend frontend build test reset clean

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	cd frontend && npm install

backend:
	.venv/bin/uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

build:
	cd frontend && npm run build

test:
	.venv/bin/python -m unittest discover -s backend/tests -v

reset:
	curl -s -X POST http://127.0.0.1:8000/api/demo/reset

clean:
	rm -rf frontend/dist backend/**/__pycache__ backend/__pycache__ .pytest_cache
	find . -name '*.pyc' -delete
