#!/bin/bash

# ═══════════════════════════════════════════════════════════════
#  MUSIC SEPARATOR - START SCRIPT avec Docker
# ═══════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  🎵 MUSIC SOURCE SEPARATOR"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Choisissez le mode de lancement:"
echo ""
echo "1) Docker (Recommandé - Tout isolé)"
echo "2) Local (Python directement)"
echo "3) Annuler"
echo ""
read -p "Votre choix (1-3): " choice

case $choice in
    1)
        echo ""
        echo -e "${BLUE}🐳 Mode Docker${NC}"
        echo ""
        
        # Use monitoring docker-compose (unified)
        COMPOSE_FILE="monitoring/docker-compose.yml"
        DOCKERFILE="dockerfile"
        echo -e "${GREEN}💻 Using unified configuration${NC}"
        echo ""
        
        # Vérifier Docker
        if ! command -v docker &> /dev/null; then
            echo -e "${RED}❌ Docker n'est pas installé${NC}"
            echo "Installer depuis: https://www.docker.com/products/docker-desktop"
            exit 1
        fi
        
        # Vérifier que Docker tourne
        if ! docker info &> /dev/null; then
            echo -e "${RED}❌ Docker n'est pas démarré${NC}"
            echo "Démarrer Docker Desktop puis relancer ce script"
            exit 1
        fi
        
        echo -e "${GREEN}✅ Docker détecté${NC}"
        echo ""
        
        # Build l'image si nécessaire
        if ! docker images | grep -q "music-separator"; then
            echo -e "${YELLOW}Image Docker non trouvée, build en cours...${NC}"
            echo "Cela peut prendre 5-10 minutes"
            echo ""
            docker build -f $DOCKERFILE -t music-separator:latest .
            echo ""
            echo -e "${GREEN}✅ Image Docker créée${NC}"
        else
            echo -e "${GREEN}✅ Image Docker trouvée${NC}"
        fi
        
        echo ""
        echo -e "${BLUE}🚀 Démarrage des conteneurs...${NC}"
        echo ""
        
        # Arrêter les anciens conteneurs si présents
        docker-compose -f $COMPOSE_FILE down 2>/dev/null || true
        
        # Démarrer avec docker-compose
        docker-compose -f $COMPOSE_FILE up -d
        
        echo ""
        echo "Attente du démarrage des services..."
        sleep 5
        
        # Vérifier API
        echo -n "Vérification API..."
        for i in {1..30}; do
            if curl -s http://localhost:8000/health > /dev/null 2>&1; then
                echo -e " ${GREEN}✅${NC}"
                break
            fi
            sleep 1
            echo -n "."
        done
        
        # Vérifier Gradio
        echo -n "Vérification Gradio..."
        for i in {1..30}; do
            if curl -s http://localhost:7860 > /dev/null 2>&1; then
                echo -e " ${GREEN}✅${NC}"
                break
            fi
            sleep 1
            echo -n "."
        done
        
        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo "  ✅ APPLICATION DÉMARRÉE (Docker)"
        echo "════════════════════════════════════════════════════════════"
        echo ""
        echo "🎨 Interface Gradio:    http://localhost:7860"
        echo "📡 API Swagger:         http://localhost:8000/docs"
        echo "❤️  Health Check:       http://localhost:8000/health"
        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo ""
        echo "Commandes utiles:"
        echo "  docker-compose logs -f     → Voir les logs"
        echo "  docker-compose down        → Arrêter"
        echo "  docker-compose restart     → Redémarrer"
        echo ""
        echo "Appuyez sur Ctrl+C pour arrêter les conteneurs"
        echo ""
        
        # Garder le script actif et afficher les logs
        trap "echo ''; echo 'Arrêt...'; docker-compose -f $COMPOSE_FILE down; exit 0" SIGINT SIGTERM
        docker-compose -f $COMPOSE_FILE logs -f
        ;;
        
    2)
        echo ""
        echo -e "${BLUE}💻 Mode Local${NC}"
        echo ""
        
        # Vérifier Python
        if ! command -v python3 &> /dev/null; then
            echo -e "${RED}❌ Python3 non trouvé${NC}"
            exit 1
        fi
        echo -e "${GREEN}✅ Python: $(python3 --version)${NC}"
        
        # Vérifier dépendances
        if ! python3 -c "import fastapi" 2>/dev/null; then
            echo -e "${YELLOW}⚠️  Dépendances manquantes${NC}"
            echo "Installer avec: pip install -r requirements.txt"
            exit 1
        fi
        echo -e "${GREEN}✅ Dépendances installées${NC}"
        echo ""
        
        # Démarrer API
        echo -e "${BLUE}🚀 Démarrage de l'API...${NC}"
        python3 -m uvicorn src.api:app --host 0.0.0.0 --port 8000 &
        API_PID=$!
        echo "API PID: $API_PID"
        
        # Attendre API
        echo -n "Attente API..."
        for i in {1..30}; do
            if curl -s http://localhost:8000/health > /dev/null 2>&1; then
                echo -e " ${GREEN}✅${NC}"
                break
            fi
            sleep 1
            echo -n "."
        done
        
        # Démarrer Gradio
        echo -e "${BLUE}🎨 Démarrage de Gradio...${NC}"
        python3 app.py &
        GRADIO_PID=$!
        echo "Gradio PID: $GRADIO_PID"
        
        # Attendre Gradio
        echo -n "Attente Gradio..."
        for i in {1..30}; do
            if curl -s http://localhost:7860 > /dev/null 2>&1; then
                echo -e " ${GREEN}✅${NC}"
                break
            fi
            sleep 1
            echo -n "."
        done
        
        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo "  ✅ APPLICATION DÉMARRÉE (Local)"
        echo "════════════════════════════════════════════════════════════"
        echo ""
        echo "🎨 Interface Gradio:    http://localhost:7860"
        echo "📡 API Swagger:         http://localhost:8000/docs"
        echo "❤️  Health Check:       http://localhost:8000/health"
        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo ""
        echo "Appuyez sur Ctrl+C pour arrêter"
        echo ""
        
        # Cleanup function
        cleanup() {
            echo ""
            echo -e "${YELLOW}🛑 Arrêt...${NC}"
            kill $API_PID 2>/dev/null || true
            kill $GRADIO_PID 2>/dev/null || true
            echo "✅ Arrêté"
            exit 0
        }
        
        trap cleanup SIGINT SIGTERM
        wait
        ;;
        
    3)
        echo "Annulé"
        exit 0
        ;;
        
    *)
        echo -e "${RED}Choix invalide${NC}"
        exit 1
        ;;
esac