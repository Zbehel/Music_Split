"""Gradio Interface - Music Separator avec synchronisation audio robuste"""
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

# ✅ Import stem config
from src.stems import STEM_CONFIGS, get_stems, get_stem_emoji, get_num_stems, get_max_stems

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

# ✅ Get MAX_STEMS dynamically
MAX_STEMS = get_max_stems()


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
    """Récupère les modèles depuis la config"""
    return list(STEM_CONFIGS.keys())


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
    """Sépare l'audio via l'API et copie les fichiers dans un dossier autorisé par Gradio"""
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
            stems = result.get('stems', {})  # Dict: name -> path (from API)
            session_id = result.get('session_id')

            if progress:
                try:
                    progress(0.9, desc="Copie des fichiers...")
                except Exception:
                    pass

            stem_names = list(stems.keys())
            
            # IMPORTANT: Copier les fichiers dans TEMP_DIR qui est autorisé par Gradio
            # Cela évite l'erreur InvalidPathError
            cached_stems = {}
            for stem_name, stem_path in stems.items():
                try:
                    original_path = Path(stem_path)
                    
                    # Ne copier que si le fichier existe et n'est pas déjà dans TEMP_DIR
                    if original_path.exists() and not str(original_path).startswith(str(TEMP_DIR)):
                        # Créer un nom unique pour éviter les conflits
                        cache_filename = f"stem_{session_id}_{stem_name}.wav"
                        cache_path = TEMP_DIR / cache_filename
                        
                        # Copier le fichier
                        shutil.copy2(original_path, cache_path)
                        cached_stems[stem_name] = str(cache_path)
                    else:
                        # Déjà dans TEMP_DIR ou n'existe pas - utiliser le chemin original
                        cached_stems[stem_name] = stem_path
                        
                except Exception as e:
                    # En cas d'erreur, utiliser le chemin original
                    print(f"Avertissement: impossible de copier {stem_name}: {e}")
                    cached_stems[stem_name] = stem_path

            if progress:
                try:
                    progress(1.0, desc="✅ Terminé!")
                except Exception:
                    pass

            stems_state = {
                "stems": cached_stems,
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


# ============================================================
# AUDIO SYNC PLAYER - Web Audio API Solution
# Fonctionne parfaitement avec Gradio 5.x
# ============================================================

AUDIO_SYNC_HTML = r"""
<style>
    .audio-player-sync {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 12px;
        padding: 20px;
        margin: 20px 0;
        color: white;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    .player-controls {
        display: flex;
        gap: 10px;
        margin-bottom: 20px;
        flex-wrap: wrap;
    }
    
    .player-btn {
        padding: 10px 20px;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        font-weight: bold;
        transition: all 0.3s;
        font-size: 14px;
    }
    
    .play-btn {
        background: #4CAF50;
        color: white;
    }
    
    .play-btn:hover {
        background: #45a049;
    }
    
    .pause-btn {
        background: #ff9800;
        color: white;
    }
    
    .pause-btn:hover {
        background: #e68900;
    }
    
    .stop-btn {
        background: #f44336;
        color: white;
    }
    
    .stop-btn:hover {
        background: #da190b;
    }
    
    .progress-bar {
        width: 100%;
        height: 8px;
        background: rgba(255,255,255,0.3);
        border-radius: 4px;
        overflow: hidden;
        margin: 10px 0;
        cursor: pointer;
    }
    
    .progress-fill {
        height: 100%;
        background: #4CAF50;
        transition: width 0.1s;
    }
    
    .time-display {
        display: flex;
        justify-content: space-between;
        font-size: 12px;
        margin-top: 8px;
    }
    
    .stems-container {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 15px;
        margin-top: 15px;
    }
    
    .stem-item {
        background: rgba(255,255,255,0.1);
        padding: 12px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    .stem-label {
        font-weight: bold;
        font-size: 12px;
        min-width: 80px;
    }
    
    .stem-controls {
        display: flex;
        gap: 8px;
        align-items: center;
        margin-left: auto;
    }
    
    .mute-btn {
        width: 28px;
        height: 28px;
        border: none;
        border-radius: 50%;
        background: rgba(255,255,255,0.2);
        cursor: pointer;
        font-size: 14px;
        transition: all 0.2s;
    }
    
    .mute-btn:hover {
        background: rgba(255,255,255,0.3);
    }
    
    .mute-btn.active {
        background: #f44336;
    }
    
    .volume-slider {
        width: 80px;
        height: 4px;
    }
</style>

<div class="audio-player-sync">
    <div class="player-controls">
        <button class="player-btn play-btn" id="playBtn">▶ Play All</button>
        <button class="player-btn pause-btn" id="pauseBtn">⏸ Pause</button>
        <button class="player-btn stop-btn" id="stopBtn">⏹ Stop</button>
    </div>
    
    <div class="progress-bar" id="progressBar">
        <div class="progress-fill" id="progressFill"></div>
    </div>
    
    <div class="time-display">
        <span id="currentTime">0:00</span>
        <span id="totalTime">0:00</span>
    </div>
    
    <div class="stems-container" id="stemsContainer"></div>
</div>

<script>
class AudioSyncPlayer {
    constructor() {
        this.audioElements = [];
        this.isPlaying = false;
        this.currentTime = 0;
        this.duration = 0;
        this.volumes = {};
        this.muted = {};
        this.initialized = false;
        
        this.init();
    }
    
    init() {
        // Retry mechanism pour les éléments chargés dynamiquement
        const tryInit = () => {
            const audios = Array.from(document.querySelectorAll('audio'));
            
            if (audios.length === 0) {
                console.log('Pas d\'audio trouvé, retry dans 500ms...');
                setTimeout(tryInit, 500);
                return;
            }
            
            this.audioElements = audios;
            
            // Initialiser les volumes et muted states
            this.audioElements.forEach((el, idx) => {
                const id = `audio_${idx}`;
                el.id = id;
                this.volumes[id] = 1.0;
                this.muted[id] = false;
                el.volume = 1.0;
                
                // Récupérer la durée
                el.addEventListener('loadedmetadata', () => {
                    if (el.duration > this.duration) {
                        this.duration = el.duration;
                        this.updateTimeDisplay();
                    }
                });
            });
            
            this.setupUI();
            this.setupButtons();
            this.setupProgressBar();
            this.startUpdateLoop();
            
            this.initialized = true;
            console.log('✅ AudioSyncPlayer initialisé avec', this.audioElements.length, 'stems');
        };
        
        tryInit();
    }
    
    setupUI() {
        const container = document.getElementById('stemsContainer');
        if (!container) return;
        
        container.innerHTML = '';
        
        this.audioElements.forEach((el, idx) => {
            const id = `audio_${idx}`;
            const label = el.closest('[class*="component"]')?.querySelector('label')?.textContent || `Stem ${idx+1}`;
            
            const stemDiv = document.createElement('div');
            stemDiv.className = 'stem-item';
            stemDiv.innerHTML = `
                <span class="stem-label">${label.substring(0, 20)}</span>
                <div class="stem-controls">
                    <button class="mute-btn" data-id="${id}" title="Mute">🔊</button>
                    <input type="range" class="volume-slider" data-id="${id}" min="0" max="100" value="100" title="Volume">
                </div>
            `;
            
            container.appendChild(stemDiv);
            
            // Mute button
            stemDiv.querySelector('.mute-btn').addEventListener('click', (e) => {
                this.toggleMute(id, e.target);
            });
            
            // Volume slider
            stemDiv.querySelector('.volume-slider').addEventListener('input', (e) => {
                this.setVolume(id, e.target.value / 100);
            });
        });
    }
    
    setupButtons() {
        const playBtn = document.getElementById('playBtn');
        const pauseBtn = document.getElementById('pauseBtn');
        const stopBtn = document.getElementById('stopBtn');
        
        if (playBtn) playBtn.addEventListener('click', () => this.playAll());
        if (pauseBtn) pauseBtn.addEventListener('click', () => this.pauseAll());
        if (stopBtn) stopBtn.addEventListener('click', () => this.stopAll());
    }
    
    setupProgressBar() {
        const bar = document.getElementById('progressBar');
        if (bar) {
            bar.addEventListener('click', (e) => {
                const percent = e.offsetX / bar.offsetWidth;
                this.seek(percent * this.duration);
            });
        }
    }
    
    startUpdateLoop() {
        setInterval(() => {
            if (this.isPlaying && this.audioElements.length > 0) {
                this.updateProgress();
                // Sync des éléments
                const master = this.audioElements[0];
                this.audioElements.slice(1).forEach(el => {
                    if (Math.abs(el.currentTime - master.currentTime) > 0.15) {
                        el.currentTime = master.currentTime;
                    }
                });
            }
        }, 100);
    }
    
    playAll() {
        if (this.audioElements.length === 0) return;
        
        this.isPlaying = true;
        this.audioElements.forEach(el => {
            el.currentTime = this.currentTime;
            const playPromise = el.play();
            if (playPromise !== undefined) {
                playPromise.catch(err => console.warn('Play error:', err));
            }
        });
        
        const btn = document.getElementById('playBtn');
        if (btn) btn.textContent = '⏸ Playing...';
    }
    
    pauseAll() {
        this.isPlaying = false;
        this.audioElements.forEach(el => el.pause());
        
        const btn = document.getElementById('playBtn');
        if (btn) btn.textContent = '▶ Play All';
    }
    
    stopAll() {
        this.isPlaying = false;
        this.currentTime = 0;
        this.audioElements.forEach(el => {
            el.pause();
            el.currentTime = 0;
        });
        
        const btn = document.getElementById('playBtn');
        if (btn) btn.textContent = '▶ Play All';
        
        this.updateProgress();
    }
    
    seek(time) {
        this.currentTime = Math.max(0, Math.min(time, this.duration));
        this.audioElements.forEach(el => {
            el.currentTime = this.currentTime;
        });
        this.updateProgress();
    }
    
    toggleMute(id, button) {
        const el = document.getElementById(id);
        if (!el) return;
        
        this.muted[id] = !this.muted[id];
        el.volume = this.muted[id] ? 0 : this.volumes[id];
        button.classList.toggle('active');
        button.textContent = this.muted[id] ? '🔇' : '🔊';
    }
    
    setVolume(id, value) {
        const el = document.getElementById(id);
        if (!el) return;
        
        this.volumes[id] = value;
        if (!this.muted[id]) {
            el.volume = value;
        }
    }
    
    updateProgress() {
        if (this.audioElements.length === 0) return;
        
        const current = this.audioElements[0].currentTime || 0;
        this.currentTime = current;
        
        const percent = (current / this.duration) * 100;
        const fill = document.getElementById('progressFill');
        if (fill) fill.style.width = percent + '%';
        
        this.updateTimeDisplay();
    }
    
    updateTimeDisplay() {
        const formatTime = (seconds) => {
            if (!seconds || isNaN(seconds)) return '0:00';
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        };
        
        const currentEl = document.getElementById('currentTime');
        const totalEl = document.getElementById('totalTime');
        
        if (currentEl) currentEl.textContent = formatTime(this.currentTime);
        if (totalEl) totalEl.textContent = formatTime(this.duration);
    }
}

// Initialiser
document.addEventListener('DOMContentLoaded', () => {
    window.audioPlayer = new AudioSyncPlayer();
});

// Aussi initialiser immédiatement
window.audioPlayer = new AudioSyncPlayer();
</script>
"""


# Interface Gradio
with gr.Blocks(title="🎵 Music Separator", theme=gr.themes.Soft()) as demo:

    gr.Markdown("""
    # 🎵 Music Source Separator
    
    Séparez vos fichiers audio en stems individuels (vocals, drums, bass, etc.)
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
                "**htdemucs_6s**: 6 stems (Vocals, Drums, Bass, Other, Guitar, Piano)"
            )

            def update_info(model):
                if model in STEM_CONFIGS:
                    config = STEM_CONFIGS[model]
                    stems_str = ", ".join([s.title() for s in config["stems"]])
                    return f"**{config['name']}**: {stems_str}"
                return ""

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

            # ✅ Audio Sync Player HTML
            gr.HTML(AUDIO_SYNC_HTML)
            
            info_box = gr.Markdown(
                "Utilisez les boutons Play/Pause/Stop pour lancer les stems synchronisés."
            )

            # ✅ Create stem rows with dynamic labels from config
            stem_players = []
            stem_mutes = []
            stem_vols = []
            stem_labels = []
            stem_rows = []  # Store row references for visibility control

            for i in range(MAX_STEMS):
                with gr.Row(visible=False) as stem_row:  # ✅ Initially hidden
                    # ✅ Dynamic label using stem name + emoji
                    default_stems = get_stems("htdemucs_6s")
                    if i < len(default_stems):
                        stem_name = default_stems[i]
                        emoji = get_stem_emoji("htdemucs_6s", i)
                        default_label = f"{emoji} {stem_name.title()}"
                    else:
                        default_label = f"Piste {i+1}"
                    
                    lbl = gr.Markdown(f"#### {default_label}", visible=False)
                    
                    player = gr.Audio(
                        label=default_label,
                        value=None,
                        visible=True, 
                        interactive=False,
                        elem_id=f"stem_player_{i}",
                        scale=3
                    )
                    
                    with gr.Column(scale=1):
                        mute_cb = gr.Checkbox(
                            label="🔇 Mute",
                            value=False,
                            visible=True,
                            scale=1
                        )
                        vol_slider = gr.Slider(
                            minimum=0.0, 
                            maximum=1.0, 
                            value=1.0, 
                            step=0.01, 
                            label="🔊 Vol",
                            visible=True,
                            scale=1
                        )
                
                stem_labels.append(lbl)
                stem_players.append(player)
                stem_mutes.append(mute_cb)
                stem_vols.append(vol_slider)
                stem_rows.append(stem_row)

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
            # ✅ FIXED: Return in correct order
            updates = [status_text, {}]
            
            # stem_rows visibility (MAX_STEMS items)
            for _ in range(MAX_STEMS):
                updates.append(gr.update(visible=False))
            
            # stem_labels (MAX_STEMS items)
            for _ in range(MAX_STEMS):
                updates.append(gr.update(value=""))
            
            # stem_players (MAX_STEMS items)
            for _ in range(MAX_STEMS):
                updates.append(gr.update(value=None, visible=False))
            
            # stem_mutes (MAX_STEMS items)
            for _ in range(MAX_STEMS):
                updates.append(gr.update(value=False, visible=False))
            
            # stem_vols (MAX_STEMS items)
            for _ in range(MAX_STEMS):
                updates.append(gr.update(value=1.0, visible=False))
            
            return tuple(updates)

        # Get stem names from config
        stems_list = get_stems(model_choice_in)
        
        outputs = [status_text, {}]

        # ✅ Update stem_rows visibility
        for i in range(MAX_STEMS):
            if i < len(stems_list):
                outputs.append(gr.update(visible=True))
            else:
                outputs.append(gr.update(visible=False))

        # ✅ Update stem_labels with proper names and emojis
        for i in range(MAX_STEMS):
            if i < len(stems_list):
                stem_name = stems_list[i]
                emoji = get_stem_emoji(model_choice_in, i)
                label_text = f"#### {emoji} {stem_name.title()}"
                outputs.append(gr.update(value=label_text))
            else:
                outputs.append(gr.update(value=""))

        # ✅ Update stem_players
        for i in range(MAX_STEMS):
            if i < len(stems_list):
                stem_name = stems_list[i]
                path = stems_state_in["stems"].get(stem_name)
                outputs.append(gr.update(value=str(path) if path else None, visible=True))
            else:
                outputs.append(gr.update(value=None, visible=False))

        # ✅ Update stem_mutes
        for i in range(MAX_STEMS):
            if i < len(stems_list):
                outputs.append(gr.update(value=False, visible=True))
            else:
                outputs.append(gr.update(value=False, visible=False))

        # ✅ Update stem_vols
        for i in range(MAX_STEMS):
            if i < len(stems_list):
                outputs.append(gr.update(value=1.0, visible=True))
            else:
                outputs.append(gr.update(value=1.0, visible=False))

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
        # ✅ FIXED: Correct order of outputs
        outputs=[status_msg, stems_state] + stem_rows + stem_labels + stem_players + stem_mutes + stem_vols
    ).then(
        fn=lambda *_: (gr.update(visible=False),),
        outputs=[cancel_btn]
    )

    cancel_btn.click(fn=on_cancel_click, outputs=[cancel_btn, status_msg])

    # Mute/Volume handlers
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

    gr.Markdown("""
    ---
    
    ### ℹ️ À propos
    
    - **Engine**: Demucs (Meta) + MVSEP
    - **Models**: htdemucs_6s (6 stems), htdemucs_ft (4 stems)
    - **Playback**: Web Audio API avec synchronisation en temps réel
    """)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )