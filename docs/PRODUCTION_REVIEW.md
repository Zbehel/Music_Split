# Audit de production — Music_Split

Date: 2025-11-19
Auteur: Revue automatique (assistant)

Résumé exécutif
- Le projet fonctionne localement et fournit une API de séparation audio basée sur Demucs + PyTorch.
- Points forts: architecture claire, tests unitaires présents, monitoring Prometheus + Grafana provisionnés, manifests k8s fournis.
- Points à améliorer avant production: robustesse et scalabilité de l'API, gestion du modèle (mémoire/taille), instrumentation et alerting, sécurité des conteneurs, préparation k8s (readiness/liveness, stockage, autoscaling), optimisation image Docker.

== Revue par composant (stack) ==

**1) API — `src/api.py` (FastAPI + uvicorn)**
- Observations:
  - Implémentation FastAPI classique; endpoints pour upload/traitement existent (ex: `/separate`).
  - Probable exécution synchrone de la séparation (torch CPU/GPU) bloquant le worker Uvicorn.
  - Il y a des threads background pour métriques/cleanup; mention d'un "RabbitMQ publisher thread" (asynchrone) dans les commentaires.
- Risques / limites:
  - Si l'opération de séparation s'exécute dans le même processus (thread principal de la requête), la latence sera élevée et les requêtes concurrentes s'entraident mal — surtout sur CPU.
  - Uvicorn/uvloop gère l'IO asynchrone mais pas l'exécution CPU lourde — qui doit être déplacée hors du loop (process pool / external worker).
- Recommandations:
  - Ne pas exécuter la séparation lourde directement dans le handler HTTP. Utiliser une queue asynchrone (RabbitMQ/Redis+RQ/Celery) ou un pool de processus avec worker dédiés.
  - Transformer les endpoints en endpoints asynchrones qui renvoient rapidement un `job_id` et fournir un endpoint `GET /status/{job_id}` + `GET /download/{job_id}/{stem}`.
  - Si vous gardez synchrone pour simplicité, documenter une `MAX_CONCURRENCY=1` et configurer Uvicorn/gunicorn avec plusieurs worker processes (prefer gunicorn + uvicorn workers) et limits mémoire.
  - Use `async` for IO-bound parts (upload, save to disk, streaming response) and offload CPU-bound parts.
  - Manipulation des fichiers: utiliser `streaming` upload & `TemporaryDirectory` pour éviter d'avoir de gros fichiers en mémoire.
  - Ajouter timeouts (request, processing) et circuit-breaker/queue-length rejection.

**2) Modèle ML — Demucs / PyTorch (`requirements.txt`)**
- Observations:
  - Utilise `demucs` + `torch` + `torchaudio`. Modèle volumineux sur disque / mémoire.
  - Dockerfile télécharge le modèle au build: pratique pour éviter runtime downloads mais image devient très lourde.
- Risques / limites:
  - Modèles PyTorch peuvent consommer beaucoup de RAM et GPU; sur CPU c'est lent.
  - GPU vs CPU image: image `pytorch/pytorch` fournie; mais pour cloud on souhaitera versions adaptées (CUDA matching drivers) ou image CPU légère.
- Recommandations:
  - Pour production CPU: envisager conversion au format ONNX + `onnxruntime` (souvent plus rapide sur CPU) ou quantization (float16/INT8) si possible.
  - Pour GPU: utiliser images et orchestration qui correspondent à la version CUDA sur le cluster (GKE avec GPU nodes ou GKE-Autopilot + GPU).
  - Implémenter `model cache`: charger le modèle une seule fois par processus worker et réutiliser.
  - Mesurer empreinte mémoire et temps de chargement; enregistrer `model_load_time`, `model_memory_bytes`.
  - Préchauffer / pré-charger le modèle (warmup) au démarrage pour réduire latences initiales.

**3) Traitement audio & dépendances (torchaudio, soundfile, numpy)**
- Observations:
  - Dépendances sensibles à versions (numpy>=2; torchaudio/tensor versions correspondent à torch).
  - I/O audio (libs C) doivent être robustes pour formats divers.
- Recommandations:
  - Valider encodages d'entrée et limiter formats acceptés.
  - Vérifier `soundfile` et `ffmpeg` disponibles dans container (Dockerfile installe `ffmpeg` — bon).
  - Ajouter validation de taille/durée avant de charger en mémoire (bloquer fichiers > MAX_FILE_SIZE / MAX_DURATION_SECONDS).

**4) Interface utilisateur (Gradio) — `app.py`**
- Observations:
  - Permet démos locales; utile pour debug et tests utilisateurs.
- Recommandations:
  - Ne pas exposer Gradio en production directement (sécurité). Garder Gradio pour UI interne ou mode démo behind auth.

**5) Docker**
- Observations:
  - `dockerfile` utilise `pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime` et installe model at build.
- Recommandations:
  - Multi-stage build pour réduire la taille: builder télécharge modèle/compiles éventuels, runtime conteneur plus léger avec seulement artefacts requis.
  - Pour CPU-only production, baser sur `python:3.x-slim` et utiliser ONNX runtime.
  - Sécurité: ajouter utilisateur non-root, limiter capabilities, minimiser layers.
  - Do not bake secrets into image.

**6) Kubernetes (`k8s/`)**
- Observations:
  - Manifests fournis (deployment, production, staging).
- Production-readiness checklist (à valider):
  - ReadinessProbe / LivenessProbe: ajouter endpoints `/health` pour vérifier que le service et/ou modèle est chargé.
  - Resource requests & limits: définir `resources.requests` et `resources.limits` CPU/MEM pour éviter OOM et permettre scheduler.
  - PersistentVolumeClaim: externaliser `results/` et `models/` si besoin (éviter local ephemeral storage pour résultats importants).
  - Autoscaling: HPA sur `cpu` ou métrique custom (queue length). Attention: scaling horizontal de service qui utilise GPU n'est pas trivial.
  - NodeSelectors & Tolerations: pour scheduler pods sur nodes avec GPU.
  - Rolling updates & probes: préparer strategy `RollingUpdate` + readiness check qui attend le modèle chargé.
  - Avoid embedding large models in image; prefer shared model-store (GCS/S3) + init container qui télécharge sur PVC.
  - Add proper RBAC, NetworkPolicy, and secure Ingress with TLS.

**7) Observability — Prometheus + Grafana (`monitoring/`, `grafana/`)**
- Observations:
  - Stack monitoring déjà en place (Prometheus config + Grafana dashboard JSON).
  - Fichiers `monitoring/alert_rules.yml` etc. présents.
- Metrics à ajouter et panels utiles:
  - Request-level:
    - `api_requests_total{method,endpoint,status}` (counter)
    - `api_request_duration_seconds` (histogram) — latence per endpoint
    - `in_progress_requests` (gauge)
  - Job-level:
    - `separation_jobs_total{status}` (counter: success/failure)
    - `separation_job_duration_seconds` (histogram)
    - `separation_queue_length` (gauge) if using job queue
    - `separation_active_jobs` (gauge)
  - Model-level:
    - `model_load_time_seconds` (gauge or summary)
    - `model_memory_bytes` (gauge)
    - `model_loaded{model}` (gauge: 0/1)
  - Resource-level (node/pod): CPU %, memory %, disk % (Prometheus node exporter / cadvisor).
  - Audio-specific:
    - `input_audio_duration_seconds` (histogram)
    - `input_audio_size_bytes` (histogram)
    - `stems_count_processed` (counter)
  - Errors & retries:
    - `separation_errors_total{type}`
    - `retry_exhausted_total`
  - Infrastructure:
    - `queue_backlog` (gauge)
    - `gpu_utilization_percent` (if GPU present)
- Alerting suggestions:
  - High error rate (e.g., >5% in 5m)
  - High median latency (P95) above SLO
  - Queue backlog > threshold for 10m
  - Pod restarts / OOM events
  - Disk space low on persistent volumes
- Dashboard ideas for Grafana:
  - Overview: requests, errors, P50/P95 latencies
  - Jobs: active jobs, queue length, job duration histogram
  - Model: load time, memory usage, model version(s) loaded
  - Nodes: CPU, memory, GPU usage
  - Alerts & recent failures

**8) Logging (`logging_config.py` / `src/logging_config.py`)**
- Observations:
  - Fichier `logging_config.py` propose formatter structuré JSON — excellent pour log collection.
- Recommandations:
  - Enrichir logs avec `request_id` / `trace_id` (corrélation entre logs & traces & metrics).
  - Log minimal utile: endpoint, method, status, duration, audio_duration, model used, job_id, input_size, error stack traces.
  - Séparer logs de debug/info/error et envoyer en JSON (bien pour ingestion dans ELK/Cloud Logging).
  - Sanitize: ne pas logger fichiers audio binary content ou secrets.
  - Intégrer traces (OpenTelemetry) pour corrélation request→job→model ops.

**9) Résilience (`resilience.py`)**
- Observations:
  - Patterns présents: retry, circuit breaker, rate limiter, timeout — très bon.
- Recommandations:
  - Utiliser ces patterns autour des appels externes (downloading youtube, model fetch, S3/GCS) et autour du worker queue.
  - Documenter paramétrage et seuils (e.g., circuit breaker open after N failures, cooldown).

**10) CI / Tests**
- Observations:
  - Tests unitaires présents; `pytest.ini` configuré.
- Recommandations:
  - Ajouter tests d'intégration qui simulent upload→separation (mock modèle pour vitesse)
  - Ajouter tests de charge ou smoke tests dans CI (sanity images build/test).
  - Ajouter linting/format (black already present in `requirements-dev`), et checks de sécurité (bandit, snyk/clair for images).

**11) Sécurité**
- Recommandations clés:
  - Secrets: utiliser `K8S Secrets` / `GCP Secret Manager`, ne pas committer `.env` en repo (vérifier `.gitignore`).
  - API: ajouter authentification (token/API key) si exposé publiquement.
  - Images: scanner vulnerability, exécuter non-root, drop capabilities.
  - NetworkPolicy: restreindre communication aux services nécessaires.

== Checklist « Prêt pour production » (prioritaire) ==
- [ ] Découpler traitement CPU intensif du thread HTTP (queue / workers).
- [ ] Endpoints asynchrones avec job id + status + retrieval.
- [ ] Définir `resources.requests/limits` et probes `readiness` / `liveness` dans `k8s/*`.
- [ ] Instrumentation Prometheus (metrics list ci-dessus) et dashboards Grafana.
- [ ] Alerts basiques: erreurs élevées, P95 > SLO, queue backlog, OOM, disk usage.
- [ ] Sécuriser l'image Docker (non-root), secrets, TLS pour Ingress.
- [ ] Tests d'intégration & pipeline CI qui build l'image et exécute smoke tests.
- [ ] Plan de stockage pour `results/` (PVC, GCS/S3) et cycle de rétention.

== Recommandations d'implémentation concrètes (extraits) ==
- Architecture traitement asynchrone (schéma simple):
  - API (FastAPI) reçoit fichier → push job dans RabbitMQ/Redis → worker pool (separators) récupère job, traite, écrit résultats sur PVC ou GCS → API expose `download` pour récupérer les stems.
- Uvicorn/Gunicorn config conseillée (si vous gardez sync handlers):
  - `gunicorn -k uvicorn.workers.UvicornWorker -w <num_workers> --threads 2 src.api:app`
  - Ajuster `num_workers` par mémoire (chaque worker charge un modèle si nécessaire). Mieux: workers légers + workers de traitement séparés.
- Monitoring & metrics:
  - Utiliser `prometheus_client` et exposer `/metrics`.
  - Instrumenter handlers avec decorator mesurant latence, taille d'entrée, model used.
- Docker:
  - Exemple multi-stage (builder télécharge et exporte modèle, runtime copie juste le modèle et app).
  - Ajouter `USER appuser` et `RUN groupadd && useradd`.
- Kubernetes:
  - Readiness probe `/health/ready` qui renvoie 200 seulement si le modèle est chargé.
  - Liveness probe `/health/live` simple.
  - HPA sur custom metric `queue_length` ou `cpu`.

== Migration Minikube → Cloud (GKE / Google Cloud) ==
- Ce qu'il faut valider:
  - Images: héberger sur Container Registry / Artifact Registry.
  - Storage: utiliser `GCS` pour modèles/outputs (ou `GCE Persistent Disks` via PVC).
  - Secrets: utiliser `Secret Manager` + Kubernetes secrets synch.
  - Autoscaling: GKE + HPA; si GPU, prévoir node pool GPU avec drivers NVIDIA installés (GPU node pool + device plugin).
  - Load balancing / TLS: utiliser Ingress + Managed Certs ou Cloud Load Balancer.
  - Observability: connecter Prometheus/Grafana à Stackdriver / Cloud Monitoring si souhaité.
- Conseils coût/perf:
  - Pour charges CPU-only légères, `Cloud Run` (serverless) peut être plus rentable si vous transformez tout en request-driven et OK cold-starts.
  - Pour besoin GPU, GKE avec GPU node pools; privilégier spot/preemptible nodes pour coût réduit (tolérance aux interruptions requise).

== Suggestions métriques + panels Grafana (liste concise) ==
- `api_requests_total`, `api_request_duration_seconds` (histogram), `api_request_in_progress`
- `separation_jobs_total{status}`, `separation_job_duration_seconds`
- `model_loaded`, `model_load_time_seconds`, `model_memory_bytes`
- `input_audio_duration_seconds`, `input_audio_size_bytes`
- `queue_length`, `active_workers`
- Node metrics: `node_cpu_util`, `node_memory_usage`, `node_disk_usage`, `gpu_util`

== Priorités (court terme → moyen terme) ==
- Court terme (1-2 sprints)
  - Découpler traitement CPU (queue + workers) — critique.
  - Ajouter metrics clés et exporter `/metrics`.
  - Ajouter readiness/liveness probes + resources limits sur k8s manifests.
  - Ajouter request size/duration limits et validations.
- Moyen terme (2-6 sprints)
  - Conversion ONNX / quantization si CPU-only.
  - CI: image build + vulnerability scan + integration tests.
  - Storage & retention policy (PVC/GCS), cleanup jobs.
- Long terme
  - Traces (OpenTelemetry), distributed tracing.
  - Autoscaling par queue-based custom metrics.
  - Canary deploys, blue/green, chaos testing pour résilience.

== Annexe: fichiers à inspecter / modifier en priorité ==
- `src/api.py` — découpler traitement
- `src/separator.py` — s'assurer que `MusicSeparator` supporte réutilisation du modèle par process
- `dockerfile` — multi-stage + non-root
- `k8s/deployment.yaml` et `k8s/production/deployment.yaml` — probes, resources, PVC
- `monitoring/` et `grafana/` — ajouter panels/alerts
- `src/logging_config.py` — ajouter request_id et JSON structured logs

---

Si vous voulez, je peux:
- Générer une PR initiale qui modifie `src/api.py` pour retourner un `job_id` et pousser les jobs dans Redis/RQ (implémentation simple). Ou
- Ajouter instrumentation Prometheus minimale dans `src/api.py` et un dashboard Grafana example.

Quelle action préférez-vous en premier ?
