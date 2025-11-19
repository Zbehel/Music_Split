# 📁 Project Structure

## Overview
Projet refactorisé pour plus de clarté et maintenabilité.

## Directory Layout

```
Music_Split/
├── src/                    # Code source Python
│   ├── api.py             # API FastAPI
│   ├── separator.py       # Logic de séparation audio
│   ├── metrics.py         # Métriques Prometheus
│   ├── logging_config.py  # Configuration logging
│   ├── resilience.py      # Patterns de résilience
│   ├── stems.py           # Config des stems
│   └── config.py          # Configuration générale
│
├── monitoring/            # Stack de monitoring complète
│   ├── docker-compose.yml # Compose avec Prometheus/Grafana
│   ├── prometheus.yml     # Config Prometheus
│   ├── alert_rules.yml    # Règles d'alertes
│   └── alertmanager.yml   # Config Alertmanager
│
├── scripts/              # Scripts utilitaires
│   ├── start.sh          # Script de démarrage principal
│   └── debug-api.sh      # Script de debug API
│
├── grafana/              # Dashboards Grafana
│   ├── dashboards/
│   └── datasources/
│
├── dockerfile            # Dockerfile principal (multi-arch)
├── requirements.txt      # Dépendances Python unifiées
├── app.py               # Interface Gradio
└── .dockerignore        # Exclusions Docker build
```

## Quick Start

### 🚀 Démarrage rapide avec monitoring

```bash
cd monitoring/
docker compose up -d
```

**Services disponibles:**
- API: http://localhost:8000
- Gradio UI: http://localhost:7860
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Alertmanager: http://localhost:9093

### 📊 Monitoring uniquement

```bash
cd monitoring/
docker compose up prometheus grafana -d
```

### 🛠️ Développement local

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer l'API
uvicorn src.api:app --reload

# Lancer Gradio
python app.py
```

## Configuration Changes

### ⚠️ Important
- **Unified Dockerfile**: Un seul Dockerfile pour toutes les architectures
- **Unified docker-compose**: Tout dans `monitoring/docker-compose.yml`
- **Unified requirements**: Un seul fichier `requirements.txt`

### Removed Files
- ❌ `dockerfile.arm64` (merged into main dockerfile)
- ❌ `docker-compose.arm64.yml` (merged)
- ❌ `docker-compose.yml` (moved to monitoring/)
- ❌ `requirements-monitoring.txt` (merged)
- ❌ `requirements-dev.txt` (merged)
- ❌ Kubernetes configs (`k8s/`, setup scripts)

## Monitoring Stack

La stack complète de monitoring inclut:

1. **Prometheus** - Collecte de métriques
2. **Grafana** - Visualisation
3. **Node Exporter** - Métriques système
4. **cAdvisor** - Métriques containers
5. **Alertmanager** - Gestion des alertes

## Development Workflow

```bash
# 1. Modifier le code dans src/
vim src/api.py

# 2. Redémarrer le service (le code est monté en volume)
cd monitoring/
docker compose restart api

# 3. Vérifier les logs
docker compose logs -f api

# 4. Tester
curl http://localhost:8000/health
```

## Docker Build

Le build Docker est optimisé avec `.dockerignore` qui exclut:
- Scripts et configs
- Documentation
- Fichiers temporaires
- Cache Python

## Troubleshooting

### Problème de healthcheck
```bash
# Vérifier que curl est installé dans le container
docker exec music-separator-api curl -f http://localhost:8000/health
```

### Rebuild complet
```bash
cd monitoring/
docker compose down
docker compose build --no-cache
docker compose up -d
```
