#!/bin/bash

# ═══════════════════════════════════════════════════════════════
#  MUSIC SEPARATOR - MINIKUBE SETUP SCRIPT
#  Ce script installe et configure tout automatiquement
# ═══════════════════════════════════════════════════════════════

set -e  # Arrêter si erreur

# Couleurs pour output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variables
IMAGE_NAME="music-separator"
IMAGE_TAG="v2.0"
NAMESPACE="music-separation"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  🚀 MUSIC SEPARATOR - MINIKUBE SETUP"
echo "════════════════════════════════════════════════════════════"
echo ""

# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 1: VÉRIFICATIONS PRÉALABLES
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}📋 Étape 1/6: Vérifications préalables...${NC}"
echo ""

# Vérifier si Docker est installé
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker n'est pas installé${NC}"
    echo "Installer Docker Desktop depuis: https://www.docker.com/products/docker-desktop"
    exit 1
fi
echo -e "${GREEN}✅ Docker trouvé: $(docker --version)${NC}"

# Vérifier si kubectl est installé
if ! command -v kubectl &> /dev/null; then
    echo -e "${YELLOW}⚠️  kubectl non trouvé, installation...${NC}"
    brew install kubectl
fi
echo -e "${GREEN}✅ kubectl trouvé: $(kubectl version --client --short 2>/dev/null || kubectl version --client)${NC}"

# Vérifier si minikube est installé
if ! command -v minikube &> /dev/null; then
    echo -e "${YELLOW}⚠️  minikube non trouvé, installation...${NC}"
    brew install minikube
fi
echo -e "${GREEN}✅ minikube trouvé: $(minikube version --short)${NC}"

echo ""
sleep 2

# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 2: DÉMARRAGE MINIKUBE
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}🎮 Étape 2/6: Démarrage Minikube...${NC}"
echo ""

# Vérifier si Minikube est déjà en cours
if minikube status &> /dev/null; then
    echo -e "${YELLOW}⚠️  Minikube est déjà en cours d'exécution${NC}"
    echo "Voulez-vous le redémarrer ? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo "Arrêt de Minikube..."
        minikube stop
        echo "Démarrage de Minikube..."
        minikube start --cpus=4 --memory=8192 --disk-size=20g --driver=docker
    fi
else
    echo "Démarrage de Minikube avec:"
    echo "  - 4 CPUs"
    echo "  - 8 GB RAM"
    echo "  - 20 GB Disk"
    echo ""
    minikube start --cpus=4 --memory=8192 --disk-size=20g --driver=docker
fi

# Vérifier le statut
echo ""
echo "Vérification du statut..."
minikube status

echo -e "${GREEN}✅ Minikube démarré avec succès${NC}"
echo ""
sleep 2

# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 3: BUILD IMAGE DOCKER
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}🐳 Étape 3/6: Build de l'image Docker...${NC}"
echo ""

# Vérifier si l'image existe déjà
if docker images | grep -q "$IMAGE_NAME.*$IMAGE_TAG"; then
    echo -e "${YELLOW}⚠️  L'image $IMAGE_NAME:$IMAGE_TAG existe déjà${NC}"
    echo "Voulez-vous la rebuilder ? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo "Build de l'image Docker..."
        docker build -t $IMAGE_NAME:$IMAGE_TAG .
    else
        echo "Utilisation de l'image existante"
    fi
else
    echo "Build de l'image Docker (cela peut prendre 5-10 minutes)..."
    docker build -t $IMAGE_NAME:$IMAGE_TAG .
fi

echo -e "${GREEN}✅ Image Docker prête${NC}"
echo ""
sleep 2

# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 4: CHARGER IMAGE DANS MINIKUBE
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}📦 Étape 4/6: Chargement de l'image dans Minikube...${NC}"
echo ""

echo "Chargement de $IMAGE_NAME:$IMAGE_TAG dans Minikube..."
echo "(Cela peut prendre 2-3 minutes)"
minikube image load $IMAGE_NAME:$IMAGE_TAG

# Vérifier que l'image est chargée
echo ""
echo "Vérification des images dans Minikube:"
minikube image ls | grep $IMAGE_NAME || echo "Image chargée mais pas visible (normal)"

echo -e "${GREEN}✅ Image chargée dans Minikube${NC}"
echo ""
sleep 2

# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 5: DÉPLOIEMENT KUBERNETES
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}☸️  Étape 5/6: Déploiement sur Kubernetes...${NC}"
echo ""

# Vérifier que les fichiers K8s existent
if [ ! -f "k8s/namespace.yaml" ]; then
    echo -e "${RED}❌ Fichier k8s/namespace.yaml non trouvé${NC}"
    exit 1
fi

if [ ! -f "k8s/deployment.yaml" ]; then
    echo -e "${RED}❌ Fichier k8s/deployment.yaml non trouvé${NC}"
    exit 1
fi

# Créer le namespace
echo "Création du namespace $NAMESPACE..."
kubectl apply -f k8s/namespace.yaml

# Déployer l'application
echo ""
echo "Déploiement de l'application..."
kubectl apply -f k8s/deployment.yaml

# Attendre que les pods soient prêts
echo ""
echo "Attente que les pods soient prêts (peut prendre 2-3 minutes)..."
kubectl wait --for=condition=ready pod \
  -l app=music-separator \
  -n $NAMESPACE \
  --timeout=300s || {
    echo -e "${YELLOW}⚠️  Timeout atteint, vérification manuelle nécessaire${NC}"
}

echo -e "${GREEN}✅ Déploiement terminé${NC}"
echo ""
sleep 2

# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 6: VÉRIFICATIONS ET INFORMATIONS
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}🔍 Étape 6/6: Vérifications finales...${NC}"
echo ""

# Afficher les pods
echo "════════════════════════════════════════════════════════════"
echo "📊 PODS"
echo "════════════════════════════════════════════════════════════"
kubectl get pods -n $NAMESPACE
echo ""

# Afficher les services
echo "════════════════════════════════════════════════════════════"
echo "🌐 SERVICES"
echo "════════════════════════════════════════════════════════════"
kubectl get services -n $NAMESPACE
echo ""

# Afficher les deployments
echo "════════════════════════════════════════════════════════════"
echo "🚀 DEPLOYMENTS"
echo "════════════════════════════════════════════════════════════"
kubectl get deployments -n $NAMESPACE
echo ""

# Vérifier si les pods sont running
POD_STATUS=$(kubectl get pods -n $NAMESPACE -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Unknown")

if [ "$POD_STATUS" = "Running" ]; then
    echo -e "${GREEN}✅ Les pods sont en cours d'exécution !${NC}"
    echo ""
    
    # ═══════════════════════════════════════════════════════════════
    #  INSTRUCTIONS D'ACCÈS
    # ═══════════════════════════════════════════════════════════════
    
    echo "════════════════════════════════════════════════════════════"
    echo "🎉 SUCCÈS ! Votre application est déployée"
    echo "════════════════════════════════════════════════════════════"
    echo ""
    echo "Pour accéder à l'application, ouvrez un NOUVEAU terminal et lancez:"
    echo ""
    echo -e "${YELLOW}kubectl port-forward -n $NAMESPACE svc/music-separator-service 8000:80${NC}"
    echo ""
    echo "Puis visitez:"
    echo -e "${GREEN}http://localhost:8000/docs${NC}     → Swagger UI"
    echo -e "${GREEN}http://localhost:8000/health${NC}   → Health check"
    echo -e "${GREEN}http://localhost:8000/models${NC}   → Liste des modèles"
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo ""
    
    # Proposer de lancer le port-forward automatiquement
    echo "Voulez-vous lancer le port-forward maintenant ? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo ""
        echo "Lancement du port-forward..."
        echo "Appuyez sur Ctrl+C pour arrêter"
        echo ""
        sleep 2
        kubectl port-forward -n $NAMESPACE svc/music-separator-service 8000:80
    fi
    
else
    echo -e "${YELLOW}⚠️  Les pods ne sont pas encore Running (Status: $POD_STATUS)${NC}"
    echo ""
    echo "Commandes utiles pour diagnostiquer:"
    echo ""
    echo "  kubectl get pods -n $NAMESPACE"
    echo "  kubectl describe pod -n $NAMESPACE -l app=music-separator"
    echo "  kubectl logs -n $NAMESPACE -l app=music-separator"
    echo ""
fi

# ═══════════════════════════════════════════════════════════════
#  COMMANDES UTILES
# ═══════════════════════════════════════════════════════════════

echo "════════════════════════════════════════════════════════════"
echo "📚 COMMANDES UTILES"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Voir les logs:"
echo "  kubectl logs -f -n $NAMESPACE -l app=music-separator"
echo ""
echo "Voir les pods:"
echo "  kubectl get pods -n $NAMESPACE"
echo ""
echo "Voir les détails d'un pod:"
echo "  kubectl describe pod <pod-name> -n $NAMESPACE"
echo ""
echo "Redémarrer le deployment:"
echo "  kubectl rollout restart deployment/music-separator -n $NAMESPACE"
echo ""
echo "Scaler le deployment:"
echo "  kubectl scale deployment/music-separator --replicas=3 -n $NAMESPACE"
echo ""
echo "Arrêter Minikube:"
echo "  minikube stop"
echo ""
echo "Supprimer tout:"
echo "  kubectl delete namespace $NAMESPACE"
echo "  minikube delete"
echo ""
echo "════════════════════════════════════════════════════════════"
echo ""

echo -e "${GREEN}🎉 Setup terminé avec succès !${NC}"
echo ""