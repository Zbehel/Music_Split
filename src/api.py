"""
FastAPI backend pour Music Source Separator
Support Demucs + MVSEP models
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Dict, List, Optional
import tempfile
import shutil
import logging
from datetime import datetime

# ✅ Import stems config
from src.stems import STEM_CONFIGS
from src.separator import get_separator, clear_cache, MusicSeparator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Créer l'application FastAPI
app = FastAPI(
    title="Music Source Separator API",
    description="Sépare les pistes audio avec Demucs et MVSEP",
    version="2.0.0"
)

# CORS pour Gradio
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dossier temporaire pour les résultats
TEMP_DIR = Path("/tmp/music-separator")
TEMP_DIR.mkdir(exist_ok=True)


@app.get("/")
def root():
    """Page d'accueil"""
    return {
        "message": "Music Source Separator API v2.0",
        "docs": "/docs",
        "health": "/health",
        "models": "/models"
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    from src.separator import get_best_device
    import torch
    
    device = get_best_device()
    device_info = {
        "current": device,
        "cuda_available": torch.cuda.is_available(),
        "mps_available": (
            hasattr(torch.backends, 'mps') and 
            torch.backends.mps.is_available() 
            if hasattr(torch.backends, 'mps') 
            else False
        ),
    }
    
    return {
        "status": "healthy",
        "device": device,
        "device_info": device_info,
        "models_loaded": list(get_separator.__globals__.get('_loaded_models', {}).keys()),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/models")
def get_models():
    """Liste des modèles disponibles avec détails"""
    models_info = MusicSeparator.get_available_models()
    
    return {
        "models": list(models_info.keys()),
        "total": len(models_info),
        "details": models_info
    }


@app.get("/models/{model_name}")
def get_model_info(model_name: str):
    """Info sur un modèle spécifique"""
    try:
        info = MusicSeparator.get_model_info(model_name)
        return info
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/separate")
async def separate_audio(
    file: UploadFile = File(...),
    model_name: str = Form(default="htdemucs_6s")
):
    """
    Sépare un fichier audio en stems
    
    Args:
        file: Fichier audio (WAV, MP3, FLAC, etc.)
        model_name: Modèle à utiliser (htdemucs_6s, htdemucs_ft, etc.)
        
    Returns:
        JSON avec chemins des stems générés
        
    Raises:
        HTTPException: Si le modèle n'existe pas ou erreur pendant la séparation
    """
    logger.info(f"Nouvelle requête de séparation avec modèle: {model_name}")
    
    # ✅ FIXED: Check in STEM_CONFIGS instead of AVAILABLE_MODELS
    if model_name not in STEM_CONFIGS:
        available = list(STEM_CONFIGS.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Modèle '{model_name}' non disponible. "
                   f"Modèles disponibles: {available}"
        )
    
    # Créer un dossier temporaire unique
    temp_session = tempfile.mkdtemp(dir=TEMP_DIR)
    temp_path = Path(temp_session)
    
    try:
        # Sauvegarder le fichier uploadé
        input_file = temp_path / "input.wav"
        with input_file.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        
        logger.info(f"Fichier sauvegardé: {input_file}")
        
        # Créer le dossier de sortie
        output_dir = temp_path / "output"
        output_dir.mkdir(exist_ok=True)
        
        # Récupérer le séparateur (avec cache)
        separator = get_separator(model_name)
        
        # Séparer l'audio
        logger.info(f"Début de la séparation...")
        results = separator.separate(str(input_file), str(output_dir))
        
        logger.info(f"Séparation terminée: {len(results)} stems générés")
        logger.info(f"Stems: {', '.join(results.keys())}")
        
        # Retourner les chemins des fichiers
        return {
            "status": "success",
            "model_used": model_name,
            "stems_count": len(results),
            "stems": results,
            "session_id": temp_path.name
        }
        
    except Exception as e:
        logger.error(f"Erreur lors de la séparation: {str(e)}", exc_info=True)
        # Nettoyer en cas d'erreur
        shutil.rmtree(temp_path, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{session_id}/{stem_name}")
def download_stem(session_id: str, stem_name: str):
    """
    Télécharge un stem spécifique
    
    Args:
        session_id: ID de session (nom du dossier temp)
        stem_name: Nom du stem (ex: "vocals", "drums")
        
    Returns:
        FileResponse: Fichier audio WAV
        
    Raises:
        HTTPException: Si le fichier n'existe pas
    """
    file_path = TEMP_DIR / session_id / "output" / f"{stem_name}.wav"
    
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Fichier {stem_name}.wav non trouvé pour session {session_id}"
        )
    
    return FileResponse(
        path=str(file_path),
        media_type="audio/wav",
        filename=f"{stem_name}.wav"
    )


@app.post("/clear-cache")
def clear_model_cache():
    """
    Vide le cache des modèles chargés en mémoire
    
    Returns:
        Status message
    """
    logger.info("Clearing model cache...")
    clear_cache()
    return {
        "status": "success",
        "message": "Model cache cleared"
    }


@app.delete("/cleanup/{session_id}")
def cleanup_session(session_id: str):
    """
    Nettoie les fichiers temporaires d'une session
    
    Args:
        session_id: ID de session à nettoyer
        
    Returns:
        Status message
        
    Raises:
        HTTPException: Si la session n'existe pas
    """
    session_path = TEMP_DIR / session_id
    
    if session_path.exists():
        logger.info(f"Cleaning up session: {session_id}")
        shutil.rmtree(session_path)
        return {
            "status": "success",
            "message": "Session cleaned",
            "session_id": session_id
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} non trouvée"
        )


@app.post("/cleanup-all")
def cleanup_all():
    """
    Nettoie TOUS les fichiers temporaires
    
    ⚠️ WARNING: This deletes all sessions!
    
    Returns:
        Status with count of removed sessions
    """
    count = 0
    logger.warning("Cleaning up ALL sessions...")
    
    try:
        for item in TEMP_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
                count += 1
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    logger.info(f"Cleaned {count} sessions")
    return {
        "status": "success",
        "message": f"Cleaned {count} sessions",
        "sessions_removed": count
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)