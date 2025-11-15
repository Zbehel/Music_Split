# 🚀 Guide Kubernetes - Music Separator

## 📋 Table des Matières

1. [Prérequis](#prérequis)
2. [Installation Locale (Minikube)](#installation-locale-minikube)
3. [Déploiement Production](#déploiement-production)
4. [Commandes Essentielles](#commandes-essentielles)
5. [Monitoring](#monitoring)
6. [Troubleshooting](#troubleshooting)

---

## Prérequis

### Outils Requis

```bash
# Vérifier kubectl
kubectl version --client

# Vérifier Docker
docker --version

# Pour local: Minikube
minikube version
```

### Installation (si nécessaire)

```bash
# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Minikube
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube
```

---

## Installation Locale (Minikube)

### 1. Démarrer Minikube

```bash
# Démarrer avec plus de ressources
minikube start --cpus=4 --memory=8192 --disk-size=20g

# Vérifier le statut
minikube status

# Activer ingress (optionnel)
minikube addons enable ingress
```

### 2. Builder l'Image Docker

```bash
# Builder l'image
docker build -t music-separator:v2.0 .

# Charger dans Minikube
minikube image load music-separator:v2.0

# Vérifier
minikube image ls | grep music-separator
```

### 3. Déployer l'Application

```bash
# Créer le namespace
kubectl apply -f k8s/namespace.yaml

# Vérifier
kubectl get namespaces | grep music-separation

# Déployer l'application
kubectl apply -f k8s/deployment.yaml

# Attendre que les pods soient prêts
kubectl wait --for=condition=ready pod -l app=music-separator -n music-separation --timeout=300s
```

### 4. Accéder à l'Application

```bash
# Option 1: Port Forward
kubectl port-forward -n music-separation svc/music-separator-service 8000:80

# Tester
curl http://localhost:8000/health
curl http://localhost:8000/models

# Option 2: Minikube Service
minikube service music-separator-service -n music-separation

# Option 3: Obtenir l'URL
minikube service music-separator-service -n music-separation --url
```

---

## Déploiement Production

### 1. Préparer l'Environnement

```bash
# Vérifier la connexion au cluster
kubectl cluster-info

# Créer le namespace
kubectl apply -f k8s/namespace.yaml

# Créer les secrets (si nécessaire)
kubectl create secret generic api-secrets \
  --from-literal=model-name=htdemucs \
  --from-literal=device=cpu \
  -n music-separation
```

### 2. Déployer

```bash
# Déploiement production
kubectl apply -f k8s/production/deployment.yaml

# Vérifier le déploiement
kubectl rollout status deployment/music-separator -n music-separation

# Vérifier les pods
kubectl get pods -n music-separation -w
```

### 3. Vérifier les Services

```bash
# Voir tous les resources
kubectl get all -n music-separation

# Tester le service
kubectl run curl-test --image=curlimages/curl -i --rm --restart=Never -n music-separation -- \
  curl http://music-separator-service/health

# Vérifier l'ingress (si configuré)
kubectl get ingress -n music-separation
```

---

## Commandes Essentielles

### Gestion des Pods

```bash
# Lister les pods
kubectl get pods -n music-separation

# Détails d'un pod
kubectl describe pod <pod-name> -n music-separation

# Logs d'un pod
kubectl logs <pod-name> -n music-separation

# Logs en temps réel
kubectl logs -f <pod-name> -n music-separation

# Logs de tous les pods du deployment
kubectl logs -n music-separation -l app=music-separator --tail=50

# Se connecter à un pod
kubectl exec -it <pod-name> -n music-separation -- /bin/bash
```

### Gestion du Deployment

```bash
# Voir le deployment
kubectl get deployment -n music-separation

# Scaler le deployment
kubectl scale deployment music-separator --replicas=5 -n music-separation

# Mettre à jour l'image
kubectl set image deployment/music-separator \
  separator=music-separator:v2.1 \
  -n music-separation

# Vérifier le rollout
kubectl rollout status deployment/music-separator -n music-separation

# Historique des rollouts
kubectl rollout history deployment/music-separator -n music-separation

# Rollback
kubectl rollout undo deployment/music-separator -n music-separation
```

### Gestion des Services

```bash
# Lister les services
kubectl get services -n music-separation

# Détails du service
kubectl describe service music-separator-service -n music-separation

# Endpoints du service
kubectl get endpoints -n music-separation
```

### HPA (Horizontal Pod Autoscaler)

```bash
# Voir le HPA
kubectl get hpa -n music-separation

# Détails du HPA
kubectl describe hpa music-separator-hpa -n music-separation

# Activer/désactiver l'autoscaling
kubectl autoscale deployment music-separator \
  --min=2 --max=10 --cpu-percent=70 \
  -n music-separation
```

---

## Monitoring

### Métriques en Temps Réel

```bash
# CPU et mémoire des pods
kubectl top pods -n music-separation

# CPU et mémoire des nodes
kubectl top nodes

# Métriques détaillées
kubectl get --raw /apis/metrics.k8s.io/v1beta1/namespaces/music-separation/pods
```

### Events

```bash
# Voir les événements récents
kubectl get events -n music-separation --sort-by='.lastTimestamp'

# Filtrer les warnings
kubectl get events -n music-separation --field-selector type=Warning

# Suivre les événements
kubectl get events -n music-separation --watch
```

### État Général

```bash
# Dashboard complet
kubectl get all -n music-separation

# Ressources détaillées
kubectl describe namespace music-separation

# Quotas et limites
kubectl describe resourcequota -n music-separation
```

### Logs Avancés

```bash
# Logs avec timestamps
kubectl logs <pod-name> -n music-separation --timestamps

# Logs depuis les 5 dernières minutes
kubectl logs <pod-name> -n music-separation --since=5m

# Logs du conteneur précédent (si crash)
kubectl logs <pod-name> -n music-separation --previous

# Export des logs
kubectl logs <pod-name> -n music-separation > pod-logs.txt
```

---

## Troubleshooting

### Pod ne démarre pas

```bash
# 1. Vérifier l'état
kubectl get pods -n music-separation

# 2. Voir les détails
kubectl describe pod <pod-name> -n music-separation

# 3. Vérifier les événements
kubectl get events -n music-separation | grep <pod-name>

# 4. Cas courants:

# Image non trouvée
kubectl describe pod <pod-name> -n music-separation | grep "Failed to pull image"
# → Vérifier le nom de l'image et les pull secrets

# Ressources insuffisantes
kubectl describe pod <pod-name> -n music-separation | grep "Insufficient"
# → Augmenter les ressources du cluster ou réduire les requests

# Erreur de configuration
kubectl logs <pod-name> -n music-separation
# → Vérifier les ConfigMaps et Secrets
```

### Service inaccessible

```bash
# 1. Vérifier que les pods sont running
kubectl get pods -n music-separation

# 2. Vérifier le service
kubectl get svc music-separator-service -n music-separation

# 3. Vérifier les endpoints
kubectl get endpoints music-separator-service -n music-separation

# 4. Tester depuis un pod
kubectl run curl-test --image=curlimages/curl -i --rm --restart=Never -n music-separation -- \
  curl -v http://music-separator-service/health

# 5. Vérifier les labels
kubectl get pods -n music-separation --show-labels
kubectl describe svc music-separator-service -n music-separation | grep Selector
```

### Performance lente

```bash
# 1. Vérifier l'utilisation des ressources
kubectl top pods -n music-separation

# 2. Vérifier les limites
kubectl describe pod <pod-name> -n music-separation | grep -A 5 "Limits"

# 3. Vérifier le HPA
kubectl get hpa -n music-separation

# 4. Augmenter les ressources
kubectl set resources deployment music-separator \
  --limits=cpu=2,memory=4Gi \
  --requests=cpu=1,memory=2Gi \
  -n music-separation
```

### Déploiement bloqué

```bash
# 1. Voir le statut du rollout
kubectl rollout status deployment/music-separator -n music-separation

# 2. Voir l'historique
kubectl rollout history deployment/music-separator -n music-separation

# 3. Annuler le rollout
kubectl rollout undo deployment/music-separator -n music-separation

# 4. Forcer un nouveau rollout
kubectl rollout restart deployment/music-separator -n music-separation
```

### Erreurs de mémoire (OOMKilled)

```bash
# 1. Identifier les pods OOMKilled
kubectl get pods -n music-separation | grep OOMKilled

# 2. Voir les détails
kubectl describe pod <pod-name> -n music-separation | grep -A 10 "Last State"

# 3. Augmenter les limites mémoire
kubectl set resources deployment music-separator \
  --limits=memory=8Gi \
  --requests=memory=4Gi \
  -n music-separation
```

---

## Configuration Avancée

### Variables d'Environnement

```bash
# Ajouter une variable d'environnement
kubectl set env deployment/music-separator \
  MODEL_NAME=htdemucs_6s \
  -n music-separation

# Voir les variables
kubectl set env deployment/music-separator --list -n music-separation

# Utiliser un ConfigMap
kubectl create configmap app-config \
  --from-literal=model-name=htdemucs \
  --from-literal=device=cpu \
  -n music-separation
```

### Secrets

```bash
# Créer un secret
kubectl create secret generic api-secrets \
  --from-literal=api-key=your-secret-key \
  -n music-separation

# Voir les secrets (valeurs masquées)
kubectl get secrets -n music-separation

# Décoder un secret
kubectl get secret api-secrets -n music-separation -o jsonpath='{.data.api-key}' | base64 -d
```

### Persistent Volumes

```bash
# Créer un PVC
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: results-storage
  namespace: music-separation
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
EOF

# Voir les PVCs
kubectl get pvc -n music-separation
```

---

## Nettoyage

```bash
# Supprimer le deployment
kubectl delete deployment music-separator -n music-separation

# Supprimer le service
kubectl delete service music-separator-service -n music-separation

# Supprimer tout le namespace (ATTENTION!)
kubectl delete namespace music-separation

# Pour Minikube
minikube stop
minikube delete
```

---

## Scripts Utiles

### Script de Déploiement Complet

```bash
#!/bin/bash
# deploy.sh

set -e

NAMESPACE="music-separation"
IMAGE_TAG="v2.0"

echo "🚀 Déploiement de Music Separator"

# 1. Build
echo "📦 Building Docker image..."
docker build -t music-separator:$IMAGE_TAG .

# 2. Load dans Minikube (si local)
if command -v minikube &> /dev/null; then
    echo "📥 Loading image into Minikube..."
    minikube image load music-separator:$IMAGE_TAG
fi

# 3. Apply K8s
echo "☸️  Applying Kubernetes manifests..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/deployment.yaml

# 4. Wait
echo "⏳ Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod \
  -l app=music-separator \
  -n $NAMESPACE \
  --timeout=300s

# 5. Vérification
echo "✅ Deployment complete!"
kubectl get pods -n $NAMESPACE
```

### Script de Monitoring

```bash
#!/bin/bash
# monitor.sh

NAMESPACE="music-separation"

watch -n 2 "
echo '=== PODS ==='
kubectl get pods -n $NAMESPACE
echo ''
echo '=== RESOURCES ==='
kubectl top pods -n $NAMESPACE 2>/dev/null || echo 'Metrics server not available'
echo ''
echo '=== EVENTS (last 5) ==='
kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -5
"
```

---

## 📚 Ressources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [kubectl Cheat Sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/)
- [Minikube Documentation](https://minikube.sigs.k8s.io/docs/)

---

**Version**: 2.0.0  
**Dernière mise à jour**: 2024-11-15
