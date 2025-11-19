# 🚀 Minikube Setup - Music Separator

## ⚡ Quick Start (5 minutes)

```bash
# Rendre les scripts exécutables
chmod +x setup-minikube.sh cleanup-minikube.sh

# Lancer le setup complet
./setup-minikube.sh
```

Le script va automatiquement :
1. ✅ Vérifier les prérequis (Docker, kubectl, minikube)
2. ✅ Installer ce qui manque (via Homebrew)
3. ✅ Démarrer Minikube avec les bonnes ressources
4. ✅ Builder l'image Docker
5. ✅ Charger l'image dans Minikube
6. ✅ Déployer sur Kubernetes
7. ✅ Vérifier que tout fonctionne

---

## 📋 Ce Que Fait le Script

### Étape 1: Vérifications
```
✅ Docker installé ?
✅ kubectl installé ?
✅ minikube installé ?
→ Si manquant, installation automatique
```

### Étape 2: Minikube
```
Démarre avec:
- 4 CPUs
- 8 GB RAM
- 20 GB Disk
- Driver: Docker
```

### Étape 3: Build Docker
```
docker build -t music-separator:v2.0 .
```

### Étape 4: Chargement
```
minikube image load music-separator:v2.0
```

### Étape 5: Déploiement
```
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/deployment.yaml
```

### Étape 6: Vérifications
```
- Status des pods
- Status des services
- Status des deployments
```

---

## 🎯 Après le Setup

### Accéder à l'Application

Le script vous proposera de lancer automatiquement le port-forward, ou vous pouvez le faire manuellement :

```bash
# Dans un terminal séparé
kubectl port-forward -n music-separation svc/music-separator-service 8000:80
```

Puis visitez :
- http://localhost:8000/docs → Swagger UI
- http://localhost:8000/health → Health check
- http://localhost:8000/models → Liste des modèles

---

## 📊 Commandes Utiles

### Voir ce qui tourne

```bash
# Tous les pods
kubectl get pods -n music-separation

# Avec plus de détails
kubectl get pods -n music-separation -o wide

# Tous les resources
kubectl get all -n music-separation
```

### Voir les logs

```bash
# Logs d'un pod
kubectl logs -f -n music-separation -l app=music-separator

# Logs d'un pod spécifique
kubectl logs <pod-name> -n music-separation

# Logs des 50 dernières lignes
kubectl logs --tail=50 -n music-separation -l app=music-separator
```

### Décrire un pod

```bash
# Voir les détails et événements
kubectl describe pod <pod-name> -n music-separation
```

### Redémarrer

```bash
# Redémarrer le deployment
kubectl rollout restart deployment/music-separator -n music-separation

# Voir le statut du rollout
kubectl rollout status deployment/music-separator -n music-separation
```

### Scaler

```bash
# Passer à 3 replicas
kubectl scale deployment/music-separator --replicas=3 -n music-separation

# Vérifier
kubectl get pods -n music-separation
```

### Se connecter à un pod

```bash
# Ouvrir un shell dans le pod
kubectl exec -it <pod-name> -n music-separation -- /bin/bash

# Exécuter une commande
kubectl exec <pod-name> -n music-separation -- curl http://localhost:8000/health
```

---

## 🧪 Tests

### Test 1: Health Check

```bash
# Via port-forward
curl http://localhost:8000/health

# Devrait retourner:
# {"status":"healthy","device":"cpu","default_model":"htdemucs"}
```

### Test 2: Liste des Modèles

```bash
curl http://localhost:8000/models

# Devrait retourner:
# {"models":["htdemucs","htdemucs_6s",...]}
```

### Test 3: Séparation Audio

```bash
# Via Swagger UI
# http://localhost:8000/docs
# → POST /separate
# → Upload un fichier audio
# → Voir les résultats
```

---

## 🐛 Troubleshooting

### Pod en CrashLoopBackOff

```bash
# Voir les logs
kubectl logs <pod-name> -n music-separation

# Voir les événements
kubectl get events -n music-separation --sort-by='.lastTimestamp'

# Voir les détails
kubectl describe pod <pod-name> -n music-separation
```

**Causes communes** :
- Image pas trouvée → Vérifier `minikube image ls`
- Erreur au démarrage → Voir les logs
- Ressources insuffisantes → Augmenter RAM Minikube

### Image Not Found

```bash
# Rebuilder et recharger
docker build -t music-separator:v2.0 .
minikube image load music-separator:v2.0

# Redémarrer le deployment
kubectl rollout restart deployment/music-separator -n music-separation
```

### Port-forward ne marche pas

```bash
# Vérifier que le service existe
kubectl get service -n music-separation

# Vérifier que les pods sont running
kubectl get pods -n music-separation

# Essayer avec le nom du pod directement
kubectl port-forward pod/<pod-name> 8000:8000 -n music-separation
```

### Minikube ne démarre pas

```bash
# Voir les logs
minikube logs

# Supprimer et recréer
minikube delete
minikube start --cpus=4 --memory=8192 --disk-size=20g
```

---

## 🧹 Cleanup

### Script de Cleanup

```bash
./cleanup-minikube.sh
```

Options disponibles :
1. Supprimer seulement le namespace
2. Arrêter Minikube (garde les données)
3. Supprimer complètement Minikube
4. Tout nettoyer
5. Annuler

### Manuellement

```bash
# Supprimer le namespace
kubectl delete namespace music-separation

# Arrêter Minikube
minikube stop

# Supprimer Minikube
minikube delete
```

---

## 📚 Architecture Déployée

```
Minikube Cluster
├─ Namespace: music-separation
│
├─ Deployment: music-separator
│  ├─ Replicas: 2 pods
│  └─ Image: music-separator:v2.0
│     ├─ Uvicorn
│     ├─ FastAPI
│     └─ Demucs models
│
├─ Service: music-separator-service
│  ├─ Type: LoadBalancer
│  ├─ Port: 80
│  └─ TargetPort: 8000
│
└─ HPA: music-separator-hpa
   ├─ Min: 2 replicas
   ├─ Max: 10 replicas
   └─ Metric: CPU 70%
```

---

## 🎓 Pour Aller Plus Loin

### Monitoring

```bash
# Activer le dashboard Minikube
minikube dashboard

# Voir les métriques
kubectl top pods -n music-separation
kubectl top nodes
```

### Ingress (Optionnel)

```bash
# Activer l'addon ingress
minikube addons enable ingress

# Vérifier
kubectl get pods -n ingress-nginx
```

### Persistent Volume

```bash
# Créer un PVC pour les résultats
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: results-pvc
  namespace: music-separation
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
EOF
```

---

## ⚙️ Configuration Avancée

### Ressources Personnalisées

Si tu veux modifier les ressources allouées :

```bash
# Arrêter Minikube
minikube stop

# Supprimer
minikube delete

# Recréer avec d'autres valeurs
minikube start --cpus=6 --memory=16384 --disk-size=40g
```

### Multiple Nodes (Simulation)

```bash
minikube start --nodes=3 --cpus=2 --memory=4096
```

---

## 📊 Monitoring du Système

### Ressources Minikube

```bash
# Status
minikube status

# IP
minikube ip

# SSH dans le node
minikube ssh

# Ressources utilisées
minikube ssh "free -h"
minikube ssh "df -h"
```

### Kubernetes

```bash
# Métriques nodes
kubectl top nodes

# Métriques pods
kubectl top pods -n music-separation

# Events cluster
kubectl get events --all-namespaces --sort-by='.lastTimestamp'
```

---

## 🎯 Checklist de Vérification

Après le setup, vérifier que :

- [ ] Minikube est running : `minikube status`
- [ ] Namespace créé : `kubectl get namespace music-separation`
- [ ] Pods running : `kubectl get pods -n music-separation`
- [ ] Service créé : `kubectl get service -n music-separation`
- [ ] Port-forward fonctionne : `curl http://localhost:8000/health`
- [ ] API répond : Tester sur http://localhost:8000/docs

---

## 🆘 Support

### Logs Complets

```bash
# Tout sauvegarder dans un fichier
kubectl get all -n music-separation > k8s-status.txt
kubectl describe pods -n music-separation >> k8s-status.txt
kubectl logs -n music-separation -l app=music-separator >> k8s-status.txt
minikube logs >> k8s-status.txt
```

### Reset Complet

```bash
# Si tout est cassé, reset complet
minikube delete
rm -rf ~/.minikube
./setup-minikube.sh
```

---

## 📝 Notes

- **RAM Recommandée** : 8 GB minimum pour Minikube
- **Disk** : 20 GB minimum
- **Docker Desktop** : Doit être démarré avant Minikube
- **Temps de Setup** : 5-10 minutes selon connexion internet
- **Coût** : $0 (tout est local)

---

**Version** : 1.0  
**Date** : 2024-11-15  
**Status** : ✅ Prêt à l'emploi
