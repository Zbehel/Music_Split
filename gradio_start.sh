#!/bin/bash

# ═══════════════════════════════════════════════════════════════
#  MUSIC SEPARATOR - START SCRIPT
#  Lance l'API FastAPI et l'interface Gradio
# ═══════════════════════════════════════════════════════════════

set -e

# Couleurs
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

# ═══════════════════════════════════════════════════════════════
#  VÉRIFICATIONS
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}📋 Vérifications...${NC}"
echo ""

# Vérifier Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 non trouvé${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python: $(python3 --version)${NC}"

# Vérifier les dépendances
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Dépendances manquantes, installation...${NC}"
    pip install -r requirements.txt
fi
echo -e "${GREEN}✅ Dépendances installées${NC}"

echo ""

# ═══════════════════════════════════════════════════════════════
#  DÉMARRAGE API
# ═══════════════════════════════════════════════════════════════

echo -e "${BLUE}🚀 Démarrage de l'API FastAPI...${NC}"
echo ""

# Lancer l'API en arrière-plan
python3 -m uvicorn src.api:app --host 0.0.0.0 --port 8000 &
API_PID=$!

echo "API PID: $API_PID"
echo ""

# Attendre que l'API soit prête
echo "Attente du démarrage de l'API..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ API prête sur http://localhost:8000${NC}"
        break
    fi
    sleep 1
    echo -n "."
done
echo ""

# ═══════════════════════════════════════════════════════════════
#  DÉMARRAGE GRADIO
# ═══════════════════════════════════════════════════════════════

echo ""
echo -e "${BLUE}🎨 Démarrage de l'interface Gradio...${NC}"
echo ""

# Lancer Gradio en arrière-plan
python3 app.py &
GRADIO_PID=$!

echo "Gradio PID: $GRADIO_PID"
echo ""

# Attendre que Gradio soit prêt
echo "Attente du démarrage de Gradio..."
for i in {1..30}; do
    if curl -s http://localhost:7860 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Gradio prêt sur http://localhost:7860${NC}"
        break
    fi
    sleep 1
    echo -n "."
done
echo ""

# ═══════════════════════════════════════════════════════════════
#  INFORMATIONS
# ═══════════════════════════════════════════════════════════════

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ✅ APPLICATION DÉMARRÉE"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "📡 API FastAPI:"
echo "   http://localhost:8000/docs   (Swagger UI)"
echo "   http://localhost:8000/health (Health check)"
echo ""
echo "🎨 Interface Gradio:"
echo "   http://localhost:7860        (Interface utilisateur)"
echo ""
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Pour arrêter l'application, appuyez sur Ctrl+C"
echo ""

# ═══════════════════════════════════════════════════════════════
#  FONCTION DE CLEANUP
# ═══════════════════════════════════════════════════════════════

cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Arrêt de l'application...${NC}"
    
    # Tuer les processus
    if [ ! -z "$API_PID" ]; then
        kill $API_PID 2>/dev/null || true
        echo "  ✅ API arrêtée"
    fi
    
    if [ ! -z "$GRADIO_PID" ]; then
        kill $GRADIO_PID 2>/dev/null || true
        echo "  ✅ Gradio arrêté"
    fi
    
    echo ""
    echo "👋 Au revoir!"
    echo ""
    exit 0
}

# Capturer Ctrl+C
trap cleanup SIGINT SIGTERM

# Garder le script actif
wait