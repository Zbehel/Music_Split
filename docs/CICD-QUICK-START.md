# 🚀 Setup CI/CD - Guide Rapide

## ⚡ Quick Start (15 minutes)

### 1. Prérequis (5 min)

```bash
# Compte Docker Hub
https://hub.docker.com/signup

# Cluster Kubernetes accessible
kubectl cluster-info

# Repository GitHub
# Votre projet doit être sur GitHub
```

### 2. Configurer Docker Hub (3 min)

```bash
# 1. Créer un token d'accès sur Docker Hub
# https://hub.docker.com/settings/security
# → New Access Token → Nom: "GitHub Actions" → Générer

# 2. Noter le token (affiché une seule fois!)
```

### 3. Configurer GitHub Secrets (5 min)

```bash
# Aller sur GitHub: Settings → Secrets and variables → Actions

# Ajouter ces secrets:
```

| Secret | Valeur | Comment obtenir |
|--------|--------|-----------------|
| `DOCKER_USERNAME` | votre_username | Votre username Docker Hub |
| `DOCKER_PASSWORD` | votre_token | Token créé à l'étape 2 |
| `KUBE_CONFIG_STAGING` | base64_kubeconfig | Voir ci-dessous |
| `KUBE_CONFIG_PROD` | base64_kubeconfig | Voir ci-dessous |
| `STAGING_URL` | https://staging.example.com | URL de staging |
| `PROD_URL` | https://example.com | URL de production |

#### Obtenir KUBE_CONFIG encodé:

```bash
# 1. Récupérer votre kubeconfig
cat ~/.kube/config

# 2. Encoder en base64 (une seule ligne)
cat ~/.kube/config | base64 -w 0

# 3. Copier le résultat et le mettre dans le secret GitHub
```

### 4. Tester le Pipeline (2 min)

```bash
# 1. Faire un commit
git add .
git commit -m "feat: test CI/CD"
git push origin develop

# 2. Aller sur GitHub → Actions
# 3. Voir le workflow s'exécuter!
```

---

## 📊 Architecture du Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│  Push vers develop/main ou Pull Request                      │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
        ┌────────────────┐
        │  1. Tests      │ ← pytest, linting, coverage
        └────────┬───────┘
                 │ ✓
                 ▼
        ┌────────────────┐
        │  2. Build      │ ← Docker build + push
        └────────┬───────┘
                 │ ✓
                 ▼
        ┌────────────────┐
        │  3. Security   │ ← Trivy scan
        └────────┬───────┘
                 │ ✓
                 ├──────────────────────┬─────────────────────┐
                 │                      │                     │
                 ▼                      ▼                     ▼
        ┌─────────────┐       ┌──────────────┐     ┌──────────────┐
        │  develop    │       │     main     │     │      PR      │
        │             │       │              │     │              │
        │ Deploy      │       │  Deploy      │     │   Tests      │
        │ Staging     │       │  Production  │     │   Only       │
        │ (auto)      │       │  (manual)    │     │              │
        └──────┬──────┘       └──────┬───────┘     └──────────────┘
               │                     │
               ▼                     ▼
        ┌─────────────┐       ┌──────────────┐
        │ Performance │       │  Smoke Tests │
        │   Tests     │       │  + Notify    │
        └─────────────┘       └──────────────┘
```

---

## 🔄 Workflows par Branche

### Branch `develop` → Staging (Auto)

```bash
# 1. Push vers develop
git checkout develop
git pull
git merge feature/ma-feature
git push

# 2. Pipeline s'exécute automatiquement:
# ✓ Tests
# ✓ Build Docker avec tag 'develop'
# ✓ Deploy automatique sur staging
# ✓ Performance tests
```

### Branch `main` → Production (Manuel)

```bash
# 1. Créer PR de develop → main
gh pr create --base main --head develop

# 2. Pipeline s'exécute:
# ✓ Tests complets
# ✓ Build Docker avec tag 'latest'
# ✓ Security scan

# 3. Merger la PR

# 4. Approuver manuellement le déploiement:
# GitHub → Actions → Deploy to Production → Review deployments

# 5. Pipeline termine:
# ✓ Deploy sur production
# ✓ Smoke tests
# ✓ Notification Slack
```

### Pull Requests → Tests uniquement

```bash
# 1. Créer une PR
gh pr create

# 2. Pipeline s'exécute:
# ✓ Tests rapides
# ✓ Security check
# ✓ Dependency check
# ✓ Auto-labeling
# ✓ Commentaire avec résumé
```

---

## 🎯 Cas d'Usage Courants

### Déployer une Nouvelle Fonctionnalité

```bash
# 1. Créer une branche feature
git checkout -b feature/nouveau-modele
# ... développer ...
git commit -m "feat: ajouter support MVSEP"
git push

# 2. Créer PR vers develop
gh pr create --base develop

# 3. Attendre validation CI
# → Tests automatiques
# → Review code

# 4. Merger
# → Déploie automatiquement sur staging

# 5. Tester sur staging
curl https://staging.music-separator.com/models

# 6. Si OK, créer PR develop → main
gh pr create --base main --head develop

# 7. Merger et approuver déploiement prod
```

### Hotfix en Production

```bash
# 1. Créer branche hotfix depuis main
git checkout main
git pull
git checkout -b hotfix/fix-memory-leak

# 2. Fix rapide
git commit -m "fix: résoudre fuite mémoire"
git push

# 3. PR vers main
gh pr create --base main --title "Hotfix: mémoire"

# 4. Merger rapidement
# → CI/CD rapide
# → Approuver déploiement
# → Deploie en production

# 5. Merger main dans develop
git checkout develop
git merge main
git push
```

### Rollback

```bash
# Option 1: Via GitHub Actions
# Actions → Deploy to Production → Dernier succès → Re-run

# Option 2: Via kubectl
kubectl rollout undo deployment/music-separator -n music-separation

# Option 3: Via nouveau commit
git revert HEAD
git push
# → Pipeline redéploie automatiquement
```

---

## 📈 Monitoring du Pipeline

### GitHub Actions UI

```
1. Aller sur le repo GitHub
2. Onglet "Actions"
3. Voir tous les workflows
4. Cliquer sur un run pour détails
5. Voir logs de chaque job
```

### CLI GitHub

```bash
# Installer GitHub CLI
sudo apt install gh

# Login
gh auth login

# Lister les runs
gh run list

# Voir un run spécifique
gh run view <run-id>

# Voir les logs
gh run view <run-id> --log

# Re-run un workflow
gh run rerun <run-id>

# Suivre en temps réel
gh run watch <run-id>
```

### Notifications

Le pipeline envoie des notifications:
- ✅ Déploiement réussi → Slack
- ❌ Déploiement échoué → Slack
- 📊 Couverture de code → Codecov
- 🔐 Vulnérabilités → GitHub Security

---

## 🔧 Configuration Avancée

### Environnements GitHub

```yaml
# Les environnements permettent:
# - Approbations manuelles
# - Secrets spécifiques
# - Protection rules

# Créer dans: Settings → Environments

# Production environment:
# - Require reviewers: ✓ (1-6 personnes)
# - Wait timer: 0 minutes
# - Deployment branches: main only
```

### Variables d'Environnement

```yaml
# Dans le workflow .github/workflows/ci-cd.yml

env:
  DOCKER_IMAGE: music-separator    # Nom de l'image
  PYTHON_VERSION: "3.11"           # Version Python
  # Ajouter d'autres variables globales ici
```

### Matrix Strategy (Tests sur plusieurs versions)

```yaml
# Tester sur Python 3.10, 3.11, 3.12
test:
  strategy:
    matrix:
      python-version: ["3.10", "3.11", "3.12"]
  steps:
    - uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}
```

---

## 🐛 Troubleshooting

### Pipeline échoue sur "Docker login"

```bash
# Problème: Credentials invalides
# Solution:
1. Vérifier DOCKER_USERNAME correct
2. Regénérer token sur Docker Hub
3. Mettre à jour DOCKER_PASSWORD dans GitHub
```

### Pipeline échoue sur "kubectl"

```bash
# Problème: Cannot connect to cluster
# Solution:
1. Vérifier kubeconfig valide:
   cat ~/.kube/config | base64 -w 0
2. Tester localement:
   kubectl --kubeconfig=<decoded-config> get pods
3. Remettre à jour le secret GitHub
```

### Tests échouent dans CI mais pas en local

```bash
# Problème: Environnement différent
# Solution:
1. Vérifier les dépendances:
   pip freeze > requirements-ci.txt
2. Comparer avec requirements.txt
3. Nettoyer le cache pip dans CI:
   - uses: actions/setup-python@v5
     with:
       cache: 'pip'
       cache-dependency-path: requirements.txt
```

### Image Docker non trouvée

```bash
# Problème: Image pas pushée ou tag incorrect
# Solution:
1. Vérifier dans Docker Hub que l'image existe
2. Vérifier les tags dans le workflow
3. Forcer un rebuild:
   git commit --allow-empty -m "chore: force rebuild"
   git push
```

---

## 📚 Documentation Complète

Pour plus de détails, voir:
- [docs/CI-CD.md](CI-CD.md) - Documentation complète
- [docs/KUBERNETES.md](KUBERNETES.md) - Guide Kubernetes
- [.github/workflows/](../.github/workflows/) - Fichiers de workflow

---

## ✅ Checklist Post-Setup

- [ ] Secrets GitHub configurés
- [ ] Premier workflow exécuté avec succès
- [ ] Staging déployé et accessible
- [ ] Production configurée (pas encore déployée)
- [ ] Notifications testées (Slack)
- [ ] Équipe formée sur le workflow
- [ ] Documentation lue et comprise
- [ ] Plan de rollback testé

---

**🎉 Félicitations ! Votre CI/CD est opérationnel !**

**Prochaine étape**: Faire votre premier déploiement staging
```bash
git checkout -b feature/test-cicd
git commit --allow-empty -m "feat: test CI/CD"
git push origin feature/test-cicd
gh pr create --base develop
```

---

**Version**: 2.0.0  
**Contact**: [Votre équipe DevOps]
