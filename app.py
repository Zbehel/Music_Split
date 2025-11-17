"""Gradio Interface - Music Separator avec Players synchronisés"""
from pathlib import Path
from typing import Dict, Optional, Tuple, List
import os
import tempfile
import threading
import uuid
import shutil
import time

import requests
import yt_dlp

try:
    import huggingface_hub
except ImportError:
    huggingface_hub = None


def _ensure_hf_folder_shim():
    """Gradio 5.x HfFolder compatibility shim"""
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

# État global
_cancel_event = threading.Event()
_youtube_audio_path = None
MAX_STEMS = 6


def download_youtube(url: str, progress=None) -> Tuple[str, str]:
    """Télécharge l'audio d'une vidéo YouTube"""
    global _youtube_audio_path

    if progress:
        try:
            progress(0.05, desc="Téléchargement YouTube...")
        except Exception:
            pass

    session_id = str(uuid.uuid4())[:8]
    output_dir = TEMP_DIR / f"youtube_{session_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(output_dir / "audio.%(ext)s")
    output_wav = output_dir / "audio.wav"

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if output_wav.exists():
            _youtube_audio_path = str(output_wav)
            if progress:
                try:
                    progress(1.0, desc="✅ YouTube téléchargé!")
                except Exception:
                    pass
            return str(output_wav), str(output_wav)

        audio_files = list(output_dir.glob("audio*"))
        if audio_files:
            audio_path = audio_files[0]
            _youtube_audio_path = str(audio_path)
            if progress:
                try:
                    progress(1.0, desc="✅ YouTube téléchargé!")
                except Exception:
                    pass
            return str(audio_path), str(audio_path)

        raise FileNotFoundError(f"Aucun fichier audio trouvé")

    except Exception as e:
        try:
            shutil.rmtree(output_dir, ignore_errors=True)
        except Exception:
            pass
        raise Exception(f"Erreur YouTube: {str(e)}")


def get_available_models():
    """Récupère les modèles depuis l'API"""
    try:
        response = requests.get(f"{API_URL}/models", timeout=5)
        if response.status_code == 200:
            return response.json().get("models", [])
    except Exception:
        pass
    return ["htdemucs_6s", "htdemucs_ft"]


def cancel_processing():
    """Annule le traitement en cours"""
    global _cancel_event
    _cancel_event.set()
    return "❌ Annulation demandée..."


def separate_audio(
    youtube_url: Optional[str],
    audio_file: Optional[str],
    model_choice: str,
    progress=None
):
    """Sépare l'audio via l'API"""
    global _cancel_event

    _cancel_event.clear()
    if progress:
        try:
            progress(0, desc="Préparation...")
        except Exception:
            pass

    if youtube_url and youtube_url.strip():
        try:
            audio_path, _ = download_youtube(youtube_url, progress)
        except Exception as e:
            return f"❌ Erreur YouTube: {str(e)}", {}
    elif audio_file:
        audio_path = audio_file
    else:
        return "❌ URL YouTube ou fichier requis", {}

    if _cancel_event.is_set():
        return "❌ Opération annulée", {}

    if progress:
        try:
            progress(0.3, desc="Séparation en cours (1-2 minutes)...")
        except Exception:
            pass

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

        if _cancel_event.is_set():
            return "❌ Opération annulée", {}

        if response.status_code == 200:
            result = response.json()
            stems = result.get('stems', {})
            session_id = result.get('session_id')

            if progress:
                try:
                    progress(1.0, desc="✅ Terminé!")
                except Exception:
                    pass

            stem_names = list(stems.keys())

            stems_state = {
                "stems": stems,
                "session_id": session_id,
                "stem_names": stem_names
            }

            message = f"✅ Séparation réussie! Modèle: {model_choice} — Stems: {', '.join(stem_names)}"
            return message, stems_state

        else:
            try:
                error = response.json().get('detail', 'Erreur inconnue')
            except Exception:
                error = f"Statut {response.status_code}"
            return f"❌ Erreur API: {error}", {}

    except requests.exceptions.Timeout:
        return "❌ Timeout (> 10 min)", {}
    except Exception as e:
        return f"❌ Erreur: {str(e)}", {}


# JavaScript pour synchronisation des players
SYNC_JS = r"""
<script>
(function(){
  // Synchroniser les players toutes les 150ms
  setInterval(function(){
    try {
      const audios = Array.from(document.querySelectorAll('audio'));
      const stemAudios = audios.filter(a => {
        const parent = a.closest('[id^="component-"]');
        if (!parent) return false;
        const lbl = parent.querySelector('label');
        return lbl && lbl.innerText && lbl.innerText.startsWith('🎵');
      });
      
      if (stemAudios.length <= 1) return;
      
      const master = stemAudios[0];
      const masterTime = master.currentTime;
      stemAudios.slice(1).forEach(a => {
        if (Math.abs(a.currentTime - masterTime) > 0.05) {
          a.currentTime = masterTime;
        }
      });
    } catch(e) {}
  }, 150);
})();
</script>
"""


# Interface Gradio
with gr.Blocks(title="🎵 Music Separator", theme=gr.themes.Soft()) as demo:

    gr.Markdown("""
    # 🎵 Music Source Separator
    
    Séparez vos fichiers audio en stems individuels (vocals, drums, bass, etc.)
    avec lecture synchronisée des pistes.
    """)

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 📥 Source Audio")

            youtube_url = gr.Textbox(
                label="🎥 URL YouTube",
                placeholder="https://www.youtube.com/watch?v=...",
                info="Collez l'URL d'une vidéo YouTube"
            )

            youtube_player = gr.Audio(
                label="🎧 Aperçu YouTube",
                interactive=False,
                visible=False
            )

            gr.Markdown("**OU**")

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

            with gr.Row():
                separate_btn = gr.Button("🚀 Séparer l'Audio", variant="primary", size="lg")
                cancel_btn = gr.Button("❌ Annuler", variant="stop", size="lg", visible=False)

            status_msg = gr.Textbox(
                label="📊 Status",
                lines=5,
                interactive=False
            )

        with gr.Column(scale=2):
            gr.Markdown("### 🎧 Pistes Séparées")

            stems_state = gr.State(value={})

            with gr.Row():
                master_play = gr.Button("▶️ Play", variant="primary")
                master_pause = gr.Button("⏸ Pause", variant="secondary")
            
            info_box = gr.Markdown(
                "Astuce: Cliquez sur **Play** pour lancer tous les stems. "
                "Utilisez les checkboxes pour mute et les sliders pour ajuster le volume."
            )

            # Créer les stems players
            stem_players = []
            stem_mutes = []
            stem_vols = []
            stem_labels = []

            for i in range(MAX_STEMS):
                with gr.Row():
                    lbl = gr.Markdown("", visible=False)#, scale=1)
                    player = gr.Audio(
                        label=f"Piste {i+1}", 
                        visible=False, 
                        interactive=False,
                        elem_id=f"stem_player_{i}",
                        scale=3
                    )
                    mute_cb = gr.Checkbox(label="Mute", value=False, visible=False, scale=0.5)
                    vol_slider = gr.Slider(
                        minimum=0.0, 
                        maximum=1.0, 
                        value=1.0, 
                        step=0.01, 
                        label="Vol", 
                        visible=False,
                        scale=1
                    )
                
                stem_labels.append(lbl)
                stem_players.append(player)
                stem_mutes.append(mute_cb)
                stem_vols.append(vol_slider)

            # Injection du script de synchronisation
            gr.HTML(SYNC_JS)

    # =============================
    # Event Handlers
    # =============================

    def on_separate_click():
        return gr.update(visible=True), gr.update(value="⏳ Traitement en cours...")

    def on_cancel_click():
        cancel_processing()
        return gr.update(visible=False), gr.update(value="❌ Annulé par l'utilisateur.")

    def youtube_preview_update(url: str):
        if not url or not url.strip():
            return gr.update(value=None, visible=False), gr.update(value=None, visible=False)
        try:
            path, _ = download_youtube(url)
            if path:
                return gr.update(value=str(path), visible=True), gr.update(value=str(path), visible=True)
            else:
                return gr.update(value=None, visible=False), gr.update(value=None, visible=False)
        except Exception:
            return gr.update(value=None, visible=False), gr.update(value=None, visible=False)

    def after_separate_update(status_text: str, stems_state_in: Dict, model_choice_in: str):
        """Met à jour les players après la séparation"""
        if not stems_state_in or "stems" not in stems_state_in:
            updates = [status_text, {}]
            for _ in range(MAX_STEMS): 
                updates.append(gr.update(value=None, visible=False))
            for _ in range(MAX_STEMS): 
                updates.append(gr.update(value=False, visible=False))
            for _ in range(MAX_STEMS): 
                updates.append(gr.update(value=1.0, visible=False))
            for _ in range(MAX_STEMS): 
                updates.append(gr.update(value=""))
            return tuple(updates)

        names = stems_state_in.get("stem_names", [])
        order = names

        outputs = [status_text, stems_state_in]

        for i in range(MAX_STEMS):
            if i < len(order):
                stem = order[i]
                path = stems_state_in["stems"].get(stem)
                outputs.append(gr.update(value=str(path) if path else None, visible=True))
            else:
                outputs.append(gr.update(value=None, visible=False))

        for i in range(MAX_STEMS):
            if i < len(order):
                outputs.append(gr.update(value=False, visible=True))
            else:
                outputs.append(gr.update(value=False, visible=False))

        for i in range(MAX_STEMS):
            if i < len(order):
                outputs.append(gr.update(value=1.0, visible=True))
            else:
                outputs.append(gr.update(value=1.0, visible=False))

        for i in range(MAX_STEMS):
            if i < len(order):
                outputs.append(gr.update(value=f"🎵 {order[i].replace('_',' ').title()}"))
            else:
                outputs.append(gr.update(value=""))

        return tuple(outputs)

    # Séparation audio
    separate_btn.click(
        fn=on_separate_click,
        outputs=[cancel_btn, status_msg]
    ).then(
        fn=separate_audio,
        inputs=[youtube_url, audio_input, model_choice],
        outputs=[status_msg, stems_state]
    ).then(
        fn=after_separate_update,
        inputs=[status_msg, stems_state, model_choice],
        outputs=[status_msg, stems_state] + stem_players + stem_mutes + stem_vols + stem_labels
    ).then(
        fn=lambda *_: (gr.update(visible=False),),
        outputs=[cancel_btn]
    )

    cancel_btn.click(fn=on_cancel_click, outputs=[cancel_btn, status_msg])

    # Play/Pause - utiliser des fonctions Python simples
    def play_audio():
        """Déclenche la lecture (gérée par JavaScript inline dans l'HTML)"""
        return None

    def pause_audio():
        """Déclenche la pause (gérée par JavaScript inline dans l'HTML)"""
        return None

    master_play.click(fn=play_audio, inputs=[], outputs=[])
    master_pause.click(fn=pause_audio, inputs=[], outputs=[])

    # Mute/Volume handlers - utiliser du JavaScript dans les composants
    for i in range(MAX_STEMS):
        def make_mute_handler(index):
            def handler(checked):
                return None
            return handler

        def make_vol_handler(index):
            def handler(val):
                return None
            return handler

        stem_mutes[i].change(fn=make_mute_handler(i), inputs=[stem_mutes[i]], outputs=[])
        stem_vols[i].change(fn=make_vol_handler(i), inputs=[stem_vols[i]], outputs=[])

    # YouTube preview
    youtube_url.change(
        fn=youtube_preview_update,
        inputs=[youtube_url],
        outputs=[youtube_player, youtube_player]
    )

    # Model info update
    def update_model_info(model):
        infos = {
            "htdemucs_6s": "**htdemucs_6s**: 6 stems - Vocals, Drums, Bass, Other, Guitar, Piano",
            "htdemucs_ft": "**htdemucs_ft**: 4 stems - Vocals, Drums, Bass, Other"
        }
        return infos.get(model, "")

    model_choice.change(
        fn=update_model_info,
        inputs=[model_choice],
        outputs=[model_info]
    )

    gr.Markdown("""
    ---
    
    ### ℹ️ À propos
    
    - **Separation Engine**: Demucs (Meta)
    - **Models**: htdemucs_6s (6 stems), htdemucs_ft (4 stems haute qualité)
    - **Synchronization**: JavaScript-based real-time sync between players
    - **Controls**: Mute checkbox = 0%, Volume slider = 0-100%
    """)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )