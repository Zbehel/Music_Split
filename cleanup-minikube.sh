#!/bin/bash

# ═══════════════════════════════════════════════════════════════
#  MUSIC SEPARATOR - MINIKUBE CLEANUP SCRIPT
#  Nettoie et arrête proprement Minikube
# ═══════════════════════════════════════════════════════════════

set -e

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

NAMESPACE="music-separation"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  🧹 MUSIC SEPARATOR - CLEANUP"
echo "════════════════════════════════════════════════════════════"
echo ""

# Menu de choix
echo "Que voulez-vous faire ?"
echo ""
echo "1) Supprimer seulement le namespace music-separation"
echo "2) Arrêter Minikube (garde les données)"
echo "3) Supprimer complètement Minikube (⚠️  tout sera perdu)"
echo "4) Tout nettoyer (namespace + arrêt Minikube)"
echo "5) Annuler"
echo ""
read -p "Votre choix (1-5): " choice

case $choice in
    1)
        echo ""
        echo -e "${YELLOW}Suppression du namespace $NAMESPACE...${NC}"
        kubectl delete namespace $NAMESPACE --ignore-not-found=true
        echo -e "${GREEN}✅ Namespace supprimé${NC}"
        ;;
    2)
        echo ""
        echo -e "${YELLOW}Arrêt de Minikube...${NC}"
        minikube stop
        echo -e "${GREEN}✅ Minikube arrêté${NC}"
        echo ""
        echo "Pour redémarrer: minikube start"
        ;;
    3)
        echo ""
        echo -e "${RED}⚠️  ATTENTION: Cela va supprimer complètement Minikube${NC}"
        echo "Toutes les données seront perdues!"
        echo ""
        read -p "Êtes-vous sûr ? (tapez 'oui' pour confirmer): " confirm
        if [ "$confirm" = "oui" ]; then
            echo ""
            echo -e "${YELLOW}Suppression de Minikube...${NC}"
            minikube delete
            echo -e "${GREEN}✅ Minikube supprimé${NC}"
            echo ""
            echo "Pour recréer: ./setup-minikube.sh"
        else
            echo "Annulé"
        fi
        ;;
    4)
        echo ""
        echo -e "${YELLOW}Nettoyage complet...${NC}"
        echo ""
        echo "1. Suppression du namespace..."
        kubectl delete namespace $NAMESPACE --ignore-not-found=true
        echo ""
        echo "2. Arrêt de Minikube..."
        minikube stop
        echo ""
        echo -e "${GREEN}✅ Nettoyage terminé${NC}"
        echo ""
        echo "Pour redémarrer: ./setup-minikube.sh"
        ;;
    5)
        echo ""
        echo "Annulé"
        ;;
    *)
        echo ""
        echo -e "${RED}Choix invalide${NC}"
        exit 1
        ;;
esac

echo ""