### 1. Prerequis
# Vérifier que kubectl est installé
kubectl version --client

# Vérifier que vous avez un cluster (Minikube, k3s, GKE, EKS, etc.)
kubectl cluster-info

### 2. Déploiement Step-by-Step
# 1. Créer le namespace
kubectl apply -f k8s/namespace.yaml

# 2. Vérifier la création
kubectl get namespaces | grep music-separation

# 3. Builder l'image Docker (nécessaire avant de déployer)
docker build -t music-separator:v2.0 .

# 4. Si vous utilisez Minikube, charger l'image
minikube image load music-separator:v2.0

# 5. Déployer l'application
kubectl apply -f k8s/deployment.yaml

# 6. Vérifier le déploiement
kubectl get deployments -n music-separation
kubectl get pods -n music-separation
kubectl get services -n music-separation

# 7. Voir les logs
kubectl logs -n music-separation -l app=music-separator --tail=50

# 8. Port forward pour accès local
kubectl port-forward -n music-separation svc/music-separator-service 8000:80

# 9. Tester l'API
curl http://localhost:8000/health
curl http://localhost:8000/models


### 3. Commandes Utiles
# Voir l'état des pods
kubectl get pods -n music-separation -w

# Décrire un pod
kubectl describe pod <pod-name> -n music-separation

# Voir les événements
kubectl get events -n music-separation --sort-by='.lastTimestamp'

# Scaler le déploiement
kubectl scale deployment music-separator -n music-separation --replicas=3

# Redémarrer le déploiement
kubectl rollout restart deployment music-separator -n music-separation

# Voir l'historique des déploiements
kubectl rollout history deployment music-separator -n music-separation

# Rollback
kubectl rollout undo deployment music-separator -n music-separation

# Supprimer tout
kubectl delete namespace music-separation