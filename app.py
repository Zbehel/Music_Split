"""Gradio Interface - Avec YouTube Support"""
from pathlib import Path
from typing import Dict, Optional, Tuple
import os
import tempfile

import requests
import yt_dlp

try:
    import huggingface_hub  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    huggingface_hub = None


def _ensure_hf_folder_shim():
    """Gradio 5.x attend huggingface_hub.HfFolder; recrée une version compat si absente."""
    if huggingface_hub is None or hasattr(huggingface_hub, "HfFolder"):
        return

    class _CompatHfFolder:
        _token_path = Path.home() / ".cache" / "huggingface" / "token"

        @classmethod
        def _ensure_dir(cls):
            cls._token_path.parent.mkdir(parents=True, exist_ok=True)

        @classmethod
        def save_token(cls, token: str):
            cls._ensure_dir()
            cls._token_path.write_text(token or "")

        @classmethod
        def get_token(cls):
            if cls._token_path.exists():
                content = cls._token_path.read_text().strip()
                return content or None
            return None

        @classmethod
        def delete_token(cls):
            if cls._token_path.exists():
                cls._token_path.unlink()

    huggingface_hub.HfFolder = _CompatHfFolder


_ensure_hf_folder_shim()

import gradio as gr

# Configuration
API_URL = os.getenv("API_URL", "http://localhost:8000")
TEMP_DIR = Path(tempfile.gettempdir()) / "gradio-music-sep"
TEMP_DIR.mkdir(exist_ok=True)


def download_youtube(url: str, progress=gr.Progress()) -> str:
    """Télécharge l'audio d'une vidéo YouTube"""
    progress(0.1, desc="Téléchargement YouTube...")
    
    output_path = TEMP_DIR / "youtube_audio"
    output_wav = TEMP_DIR / "youtube_audio.wav"
    
    # Nettoyer anciens fichiers
    for f in TEMP_DIR.glob("youtube_audio*"):
        try:
            f.unlink()
        except:
            pass
    
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
            }],
            'outtmpl': str(output_path),
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        if output_wav.exists():
            return str(output_wav)
        
        # Fallback: chercher le fichier téléchargé
        audio_files = list(TEMP_DIR.glob("youtube_audio*"))
        if audio_files:
            return str(audio_files[0])
        
        raise FileNotFoundError("Téléchargement échoué")
        
    except Exception as e:
        raise Exception(f"Erreur YouTube: {str(e)}")


def get_available_models():
    """Récupère les modèles depuis l'API"""
    try:
        response = requests.get(f"{API_URL}/models")
        if response.status_code == 200:
            return response.json().get("models", [])
    except:
        pass
    return ["htdemucs_6s", "htdemucs_ft"]


def separate_audio(
    youtube_url: Optional[str],
    audio_file: Optional[str],
    model_choice: str,
    progress=gr.Progress()
):
    """Sépare l'audio via l'API"""
    
    progress(0, desc="Préparation...")
    
    # Déterminer la source
    if youtube_url and youtube_url.strip():
        try:
            audio_path = download_youtube(youtube_url, progress)
        except Exception as e:
            return f"❌ Erreur YouTube: {str(e)}", {}, *([None] * 10)
    elif audio_file:
        audio_path = audio_file
    else:
        return "❌ URL YouTube ou fichier requis", {}, *([None] * 10)
    
    progress(0.3, desc="Séparation en cours (1-2 minutes)...")
    
    try:
        with open(audio_path, 'rb') as f:
            files = {'file': f}
            data = {'model_name': model_choice}
            
            response = requests.post(
                f"{API_URL}/separate",
                files=files,
                data=data,
                timeout=600
            )
        
        if response.status_code == 200:
            result = response.json()
            stems = result.get('stems', {})
            session_id = result.get('session_id')
            
            progress(1.0, desc="✅ Terminé!")
            
            message = f"""
✅ Séparation réussie!

Modèle: {model_choice}
Pistes: {len(stems)}
Stems: {', '.join(stems.keys())}
            """
            
            # Préparer les sorties audio (max 10)
            audio_outputs = []
            for i in range(10):
                if i < len(stems):
                    stem_name = list(stems.keys())[i]
                    stem_path = stems[stem_name]
                    audio_outputs.append(gr.Audio(
                        value=stem_path,
                        label=f"🎵 {stem_name.replace('_', ' ').title()}",
                        visible=True
                    ))
                else:
                    audio_outputs.append(gr.Audio(visible=False))
            
            return message, {"stems": stems, "session_id": session_id}, *audio_outputs
        else:
            error = response.json().get('detail', 'Erreur inconnue')
            return f"❌ Erreur API: {error}", {}, *([None] * 10)
            
    except requests.exceptions.Timeout:
        return "❌ Timeout (> 10 min)", {}, *([None] * 10)
    except Exception as e:
        return f"❌ Erreur: {str(e)}", {}, *([None] * 10)


# Interface Gradio
with gr.Blocks(title="🎵 Music Separator", theme=gr.themes.Soft()) as demo:
    
    gr.Markdown("""
    # 🎵 Music Source Separator
    
    Séparez les pistes audio en stems individuels.
    
    **Formats supportés**: YouTube, WAV, MP3, FLAC, OGG, M4A
    """)
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 📥 Source Audio")
            
            # YouTube URL
            youtube_url = gr.Textbox(
                label="🎥 URL YouTube",
                placeholder="https://www.youtube.com/watch?v=...",
                info="Collez l'URL d'une vidéo YouTube"
            )
            
            gr.Markdown("**OU**")
            
            # Upload fichier
            audio_input = gr.Audio(
                label="📁 Fichier Audio",
                type="filepath",
                sources=["upload"]
            )
            
            gr.Markdown("### 🎛️ Configuration")
            
            model_choice = gr.Dropdown(
                choices=get_available_models(),
                value="htdemucs_6s",
                label="Modèle",
                info="Choisissez le modèle de séparation"
            )
            
            model_info = gr.Markdown(
                "**htdemucs_6s**: 6 stems (vocals, drums, bass, other, guitar, piano)"
            )
            
            def update_info(model):
                infos = {
                    "htdemucs_6s": "**htdemucs_6s**: 6 stems (vocals, drums, bass, other, guitar, piano)",
                    "htdemucs_ft": "**htdemucs_ft**: 4 stems haute qualité (vocals, drums, bass, other)"
                }
                return infos.get(model, "")
            
            model_choice.change(fn=update_info, inputs=[model_choice], outputs=[model_info])
            
            separate_btn = gr.Button("🚀 Séparer l'Audio", variant="primary", size="lg")
            
            status_msg = gr.Textbox(label="📊 Status", lines=5, interactive=False)
        
        with gr.Column(scale=2):
            gr.Markdown("### 🎧 Pistes Séparées")
            
            stems_state = gr.State(value={})
            
            # 10 lecteurs audio dynamiques
            audio_players = []
            for i in range(10):
                audio = gr.Audio(
                    label=f"Piste {i+1}",
                    visible=False,
                    interactive=False
                )
                audio_players.append(audio)
    
    # Connecter le bouton
    separate_btn.click(
        fn=separate_audio,
        inputs=[youtube_url, audio_input, model_choice],
        outputs=[status_msg, stems_state] + audio_players
    )
    
    gr.Markdown("""
    ---
    
    ### ℹ️ Informations
    
    - **Temps**: 30s à 2 min selon longueur et modèle
    - **YouTube**: Téléchargement automatique de l'audio
    - **Formats**: WAV, MP3, FLAC, OGG, M4A
    - **Durée max recommandée**: 10 minutes
    
    **Modèles**:
    - `htdemucs_6s`: 6 pistes (recommandé)
    - `htdemucs_ft`: 4 pistes haute qualité
    
    **Note**: Le modèle reste en mémoire après le premier usage.
    """)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )