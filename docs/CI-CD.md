# CI/CD Documentation

## 📋 Vue d'Ensemble

Ce projet utilise GitHub Actions pour un pipeline CI/CD complet avec :
- Tests automatiques
- Build Docker
- Scan de sécurité
- Déploiement automatique (staging) et manuel (production)
- Tests de performance

## 🔄 Workflows

### 1. CI/CD Principal (`ci-cd.yml`)

**Déclencheurs:**
- Push sur `main` ou `develop`
- Pull Request vers `main` ou `develop`
- Publication d'une release

**Jobs:**

#### Job 1: Tests & Qualité
- Installation des dépendances
- Linting avec Black
- Tests avec pytest
- Couverture de code (Codecov)

#### Job 2: Build Docker
- Build de l'image Docker
- Push vers Docker Hub
- Tags multiples (branch, version, SHA)
- Cache de build

#### Job 3: Security Scan
- Scan Trivy pour vulnérabilités
- Upload vers GitHub Security

#### Job 4: Deploy Staging
- Déploiement automatique sur `develop`
- Mise à jour du deployment Kubernetes

#### Job 5: Deploy Production
- Déploiement manuel sur `main`
- Smoke tests après déploiement
- Notifications Slack

#### Job 6: Performance Tests
- Tests de charge avec Locust
- Uniquement après deploy staging

### 2. Pull Request Checks (`pr-checks.yml`)

**Déclencheurs:**
- Ouverture/mise à jour d'une PR

**Jobs:**
- Tests rapides
- Vérification de sécurité (Bandit)
- Vérification des dépendances
- Auto-labeling
- Commentaire de résumé

## 🔐 Secrets Requis

### GitHub Secrets à configurer:

```bash
# Docker Hub
DOCKER_USERNAME=votre_username
DOCKER_PASSWORD=votre_token_dockerhub

# Kubernetes Staging
KUBE_CONFIG_STAGING=base64_encoded_kubeconfig

# Kubernetes Production
KUBE_CONFIG_PROD=base64_encoded_kubeconfig

# URLs
STAGING_URL=https://staging.music-separator.example.com
PROD_URL=https://music-separator.example.com

# Notifications (optionnel)
SLACK_WEBHOOK=https://hooks.slack.com/services/...
```

### Comment créer les secrets Kubernetes:

```bash
# 1. Récupérer votre kubeconfig
cat ~/.kube/config

# 2. Encoder en base64
cat ~/.kube/config | base64 -w 0

# 3. Ajouter dans GitHub:
# Settings → Secrets and variables → Actions → New repository secret
```

## 🚀 Workflow de Déploiement

### Développement → Staging

```bash
# 1. Créer une branche feature
git checkout -b feature/nouvelle-fonctionnalite

# 2. Développer et tester
git add .
git commit -m "feat: ajouter nouvelle fonctionnalité"
git push origin feature/nouvelle-fonctionnalite

# 3. Créer une Pull Request vers develop
# → Tests automatiques s'exécutent
# → Review du code

# 4. Merger la PR
# → Déploiement automatique sur staging
```

### Staging → Production

```bash
# 1. Créer une PR de develop vers main
git checkout main
git pull
gh pr create --base main --head develop --title "Release v2.1.0"

# 2. Review et validation
# → Tests complets s'exécutent
# → Validation manuelle requise

# 3. Merger la PR
# → Build Docker automatique
# → Déploiement MANUEL en production
#   (approval requis dans GitHub)

# 4. Vérifier le déploiement
curl https://music-separator.example.com/health
curl https://music-separator.example.com/models
```

## 📊 Monitoring du Pipeline

### Voir les workflows actifs:
```bash
# CLI GitHub
gh run list

# Voir les détails d'un run
gh run view <run-id>

# Voir les logs
gh run view <run-id> --log
```

### Dans l'interface GitHub:
1. Aller dans l'onglet "Actions"
2. Cliquer sur un workflow
3. Voir les logs de chaque job

## 🔧 Configuration Kubernetes

### Structure des environnements:

```
k8s/
├── namespace.yaml           # Namespace production de base
├── deployment.yaml          # Deployment production de base
├── staging/
│   └── deployment.yaml      # Config staging complète
└── production/
    └── deployment.yaml      # Config production optimisée
```

### Différences Staging vs Production:

| Aspect | Staging | Production |
|--------|---------|------------|
| Replicas | 1 | 3 |
| Resources | 1Gi RAM, 500m CPU | 2-4Gi RAM, 1-2 CPU |
| HPA | Non | Oui (3-10 pods) |
| PDB | Non | Oui (min 2 available) |
| Ingress | staging.* | production domain |
| Auto-deploy | ✅ Oui | ❌ Manuel |

## 🧪 Tests

### Tests locaux avant push:

```bash
# Tests complets
pytest tests/ -v

# Tests avec coverage
pytest tests/ --cov=src --cov-report=html

# Tests rapides seulement
pytest tests/ -m "not slow"

# Linting
black --check src/ tests/
```

### Tests dans CI:

```yaml
# Marquage des tests lents
@pytest.mark.slow
def test_separation_6stem(test_audio, tmp_path):
    # Test long...
```

## 🛠️ Rollback

### Rollback automatique Kubernetes:

```bash
# Voir l'historique
kubectl rollout history deployment/music-separator -n music-separation

# Rollback à la version précédente
kubectl rollout undo deployment/music-separator -n music-separation

# Rollback à une version spécifique
kubectl rollout undo deployment/music-separator -n music-separation --to-revision=3
```

### Rollback manuel via CI/CD:

1. Aller dans Actions → Deploy to Production
2. Cliquer sur le dernier déploiement réussi
3. Cliquer sur "Re-run all jobs"

## 📈 Métriques et Monitoring

### Logs en temps réel:

```bash
# Staging
kubectl logs -f -n music-separation-staging -l app=music-separator

# Production
kubectl logs -f -n music-separation -l app=music-separator

# Erreurs seulement
kubectl logs -n music-separation -l app=music-separator | grep ERROR
```

### Métriques des pods:

```bash
# Utilisation CPU/Mémoire
kubectl top pods -n music-separation

# Statut des pods
kubectl get pods -n music-separation -w
```

## 🚨 Troubleshooting

### Pipeline échoue sur les tests:

```bash
# Exécuter les tests localement
pytest tests/ -v --tb=short

# Vérifier les dépendances
pip install -r requirements-dev.txt
```

### Build Docker échoue:

```bash
# Build local
docker build -t music-separator:test .

# Vérifier les logs
docker build --progress=plain -t music-separator:test .
```

### Déploiement K8s échoue:

```bash
# Vérifier le statut
kubectl describe deployment music-separator -n music-separation

# Voir les events
kubectl get events -n music-separation --sort-by='.lastTimestamp'

# Logs du pod qui fail
kubectl logs <pod-name> -n music-separation
```

### Image Docker pas trouvée:

```bash
# Vérifier que l'image existe sur Docker Hub
docker pull <username>/music-separator:latest

# Vérifier les secrets GitHub
# Settings → Secrets → DOCKER_USERNAME et DOCKER_PASSWORD
```

## 🎯 Best Practices

### Commits:

```bash
# Utiliser conventional commits
feat: ajouter nouveau modèle MVSEP
fix: corriger bug de mémoire
docs: mettre à jour README
test: ajouter tests pour API
chore: mettre à jour dépendances
```

### Branches:

```
main          → Production
develop       → Staging
feature/*     → Nouvelles fonctionnalités
fix/*         → Bug fixes
hotfix/*      → Fixes urgents en production
```

### Tags:

```bash
# Créer un tag pour une release
git tag -a v2.0.0 -m "Release v2.0.0"
git push origin v2.0.0

# Le workflow publiera automatiquement avec ce tag
```

## 📚 Ressources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Docker Hub](https://hub.docker.com/)
- [Conventional Commits](https://www.conventionalcommits.org/)

## ✅ Checklist de Setup CI/CD

- [ ] Créer compte Docker Hub
- [ ] Configurer secrets GitHub (DOCKER_USERNAME, DOCKER_PASSWORD)
- [ ] Configurer kubeconfig pour staging
- [ ] Configurer kubeconfig pour production
- [ ] Tester build Docker localement
- [ ] Tester déploiement staging
- [ ] Configurer Slack webhook (optionnel)
- [ ] Configurer monitoring (optionnel)
- [ ] Documenter les URLs d'environnement
- [ ] Former l'équipe sur le workflow

---

**Version**: 2.0.0  
**Dernière mise à jour**: 2024-11-15
