"""Exemple minimaliste: Synchronisation audio avec Web Audio API"""
import gradio as gr

# ============================================================
# PLAYER HTML + JAVASCRIPT (tout-en-un)
# ============================================================

SYNC_PLAYER = r"""
<style>
    .player-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 12px;
        padding: 20px;
        color: white;
    }
    .controls { display: flex; gap: 10px; margin-bottom: 15px; }
    .btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; 
           font-weight: bold; transition: 0.3s; }
    .play { background: #4CAF50; } .play:hover { background: #45a049; }
    .pause { background: #ff9800; } .pause:hover { background: #e68900; }
    .stop { background: #f44336; } .stop:hover { background: #da190b; }
    .progress { width: 100%; height: 8px; background: rgba(255,255,255,0.3); 
                border-radius: 4px; overflow: hidden; cursor: pointer; margin: 10px 0; }
    .fill { height: 100%; background: #4CAF50; width: 0%; }
    .time { display: flex; justify-content: space-between; font-size: 12px; }
    .stems { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
             gap: 12px; margin-top: 15px; }
    .stem { background: rgba(255,255,255,0.1); padding: 10px; border-radius: 8px; 
            display: flex; gap: 8px; align-items: center; justify-content: space-between; }
    .mute-btn { width: 28px; height: 28px; border: none; border-radius: 50%; 
                background: rgba(255,255,255,0.2); cursor: pointer; font-size: 14px; }
    .mute-btn:hover { background: rgba(255,255,255,0.3); }
    .mute-btn.active { background: #f44336; }
    .vol { width: 60px; height: 4px; }
</style>

<div class="player-box">
    <div class="controls">
        <button class="btn play" id="play">▶ Play</button>
        <button class="btn pause" id="pause">⏸ Pause</button>
        <button class="btn stop" id="stop">⏹ Stop</button>
    </div>
    
    <div class="progress" id="prog"><div class="fill" id="fill"></div></div>
    <div class="time"><span id="cur">0:00</span><span id="tot">0:00</span></div>
    
    <div class="stems" id="stems"></div>
</div>

<script>
class Player {
    constructor() {
        this.audios = [];
        this.playing = false;
        this.time = 0;
        this.duration = 0;
        this.init();
    }
    
    init() {
        const retry = () => {
            this.audios = Array.from(document.querySelectorAll('audio'));
            if (this.audios.length === 0) {
                setTimeout(retry, 500);
                return;
            }
            this.audios.forEach(el => {
                el.addEventListener('loadedmetadata', () => {
                    if (el.duration > this.duration) {
                        this.duration = el.duration;
                        this.updateTime();
                    }
                });
            });
            this.buildUI();
            this.setupButtons();
            this.startLoop();
        };
        retry();
    }
    
    buildUI() {
        const container = document.getElementById('stems');
        this.audios.forEach((el, i) => {
            const name = el.closest('[class*="component"]')?.querySelector('label')?.textContent || `Stem ${i+1}`;
            const div = document.createElement('div');
            div.className = 'stem';
            div.innerHTML = `
                <span style="font-size: 12px; min-width: 60px;">${name.substring(0, 15)}</span>
                <button class="mute-btn" data-id="${i}">🔊</button>
                <input type="range" class="vol" data-id="${i}" min="0" max="100" value="100">
            `;
            container.appendChild(div);
            
            div.querySelector('.mute-btn').addEventListener('click', (e) => {
                const el = this.audios[i];
                el.muted = !el.muted;
                e.target.classList.toggle('active');
                e.target.textContent = el.muted ? '🔇' : '🔊';
            });
            
            div.querySelector('.vol').addEventListener('input', (e) => {
                this.audios[i].volume = e.target.value / 100;
            });
        });
    }
    
    setupButtons() {
        document.getElementById('play').addEventListener('click', () => this.play());
        document.getElementById('pause').addEventListener('click', () => this.pause());
        document.getElementById('stop').addEventListener('click', () => this.stop());
        document.getElementById('prog').addEventListener('click', (e) => {
            const percent = e.offsetX / e.currentTarget.offsetWidth;
            this.seek(percent * this.duration);
        });
    }
    
    play() {
        this.playing = true;
        this.audios.forEach(el => {
            el.currentTime = this.time;
            el.play().catch(() => {});
        });
    }
    
    pause() {
        this.playing = false;
        this.audios.forEach(el => el.pause());
    }
    
    stop() {
        this.playing = false;
        this.time = 0;
        this.audios.forEach(el => { el.pause(); el.currentTime = 0; });
        this.updateProgress();
    }
    
    seek(t) {
        this.time = t;
        this.audios.forEach(el => el.currentTime = t);
        this.updateProgress();
    }
    
    startLoop() {
        setInterval(() => {
            if (this.playing && this.audios.length > 0) {
                this.time = this.audios[0].currentTime;
                this.updateProgress();
                // Sync
                const master = this.audios[0].currentTime;
                this.audios.slice(1).forEach(el => {
                    if (Math.abs(el.currentTime - master) > 0.2) {
                        el.currentTime = master;
                    }
                });
            }
        }, 100);
    }
    
    updateProgress() {
        const pct = (this.time / this.duration) * 100;
        document.getElementById('fill').style.width = pct + '%';
        this.updateTime();
    }
    
    updateTime() {
        const fmt = (s) => {
            const m = Math.floor(s / 60);
            const ss = Math.floor(s % 60);
            return `${m}:${ss.toString().padStart(2, '0')}`;
        };
        document.getElementById('cur').textContent = fmt(this.time);
        document.getElementById('tot').textContent = fmt(this.duration);
    }
}

new Player();
</script>
"""

# ============================================================
# INTERFACE GRADIO
# ============================================================

with gr.Blocks(title="Audio Sync Player") as demo:
    gr.Markdown("# 🎵 Audio Sync Player - Exemple Minimaliste")
    
    # Upload
    audio_file = gr.File(label="📁 Upload Audio File", file_types=["audio"])
    
    gr.Markdown("### 🎧 Stems (simulés)")
    
    # Le player synchronisé
    gr.HTML(SYNC_PLAYER)
    
    # Stems players (cachés mais accessibles au script)
    with gr.Row():
        s1 = gr.Audio(value=None, visible=True, interactive=False, label="Vocals")
        s2 = gr.Audio(value=None, visible=True, interactive=False, label="")
        s3 = gr.Audio(value=None, visible=True, interactive=False, label="")
        s4 = gr.Audio(value=None, visible=True, interactive=False, label="")
    
    # Fonction pour simuler la séparation
    def process(file):
        if not file:
            return None, None, None, None
        
        # Ici on simulerait l'appel à l'API
        # Pour l'exemple, on crée 4 copies du même fichier
        return file, file, file, file
    
    audio_file.change(
        fn=process,
        inputs=audio_file,
        outputs=[s1, s2, s3, s4]
    )
    
    gr.Markdown("""
    ### Comment ça marche?
    
    1. **Upload** un fichier audio
    2. Les 4 stems s'affichent en bas (simulés)
    3. **Play/Pause/Stop** synchronise tous les stems
    4. **Barre de progression** cliquable
    5. **Volume + Mute** individuels pour chaque stem
    6. **Affichage du temps** en bas à gauche
    """)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, show_error=True)