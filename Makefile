# Reco — alias docker compose (P3.18, ADR 0037).
# Usage : `make <cible>` (tabulations exigées par make).

COMPOSE ?= docker compose

.PHONY: help build up down logs ps pipeline shell test clean rebuild

help:
	@echo "Cibles disponibles :"
	@echo "  build     - Build l'image reco:dev"
	@echo "  up        - Démarre review_server (8000) + site statique (4321)"
	@echo "  down      - Arrête les services"
	@echo "  logs      - Tail des logs (Ctrl+C pour sortir)"
	@echo "  ps        - Statut des conteneurs"
	@echo "  pipeline  - Run pipeline (build_cache + lints + audits)"
	@echo "  shell     - Shell dans le conteneur review"
	@echo "  test      - Run pytest dans le conteneur"
	@echo "  clean     - Down + suppression image + volumes"
	@echo "  rebuild   - Down + build --no-cache + up"

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

pipeline:
	$(COMPOSE) --profile pipeline run --rm reco-pipeline

shell:
	$(COMPOSE) run --rm reco-review shell

test:
	$(COMPOSE) run --rm reco-review python -m pytest tests/ -q

clean:
	$(COMPOSE) down -v
	-docker image rm reco:dev

rebuild:
	$(COMPOSE) down
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d
