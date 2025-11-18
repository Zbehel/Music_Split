"""Music Source Separator - Sans TorchCodec/FFmpeg"""
from src.stems import STEM_CONFIGS, get_stems, get_num_stems

import torch
import numpy as np
from pathlib import Path
from typing import Dict, Optional
import logging
import soundfile as sf
from demucs.pretrained import get_model
from demucs.apply import apply_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_best_device() -> str:
    """
    Détecte automatiquement le meilleur device disponible
    Priorité: CUDA > MPS > CPU
    
    Returns:
        str: 'cuda', 'mps', ou 'cpu'
    """
    if torch.cuda.is_available():
        return "cuda"
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        return "mps"
    else:
        return "cpu"


class MusicSeparator:
    # ✅ Use shared config instead of duplicating
    AVAILABLE_MODELS = {
        model_name: {
            "names": config["stems"],
            "description": config["description"],
            "type": "demucs",
            "description": config['desc']
        }
        for model_name, config in STEM_CONFIGS.items()
    }
    
    def __init__(self, model_name: str = "htdemucs_6s", device=None):
        if model_name not in self.AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {model_name}")
        
        self.model_name = model_name
        self.model_config = self.AVAILABLE_MODELS[model_name]
        self.stems = get_stems(model_name)  # ✅ Get from shared config
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.model_type = self.model_config["type"]
        
        logger.info(f"Init {model_name} sur {self.device}")
        
    def _load_model(self):
        if self.model:
            return
        logger.info(f"Chargement {self.model_name}...")
        self.model = get_model(name=self.model_name)
        self.model.to(self.device).eval()
        logger.info("✅ Chargé")
    
    def separate(self, audio_path: str, output_dir: str) -> Dict[str, str]:
        self._load_model()
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        return self._separate_demucs(audio_path, out)
    
    def _separate_demucs(self, audio_path: str, out: Path) -> Dict[str, str]:
        # Charger avec soundfile (pas de torchcodec/ffmpeg)
        audio_data, sr = sf.read(audio_path, always_2d=True)
        
        # Convertir en torch tensor (channels, samples)
        wav = torch.from_numpy(audio_data.T).float()
        
        # Resample si nécessaire
        if sr != self.model.samplerate:
            # Resample simple sans torchaudio
            import scipy.signal
            num_samples = int(wav.shape[1] * self.model.samplerate / sr)
            wav_resampled = []
            for channel in wav:
                resampled = scipy.signal.resample(channel.numpy(), num_samples)
                wav_resampled.append(torch.from_numpy(resampled))
            wav = torch.stack(wav_resampled)
        
        # Normaliser si mono → stereo
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        
        # Ajouter batch et envoyer au device
        wav = wav.unsqueeze(0).to(self.device)
        
        # Séparer
        with torch.no_grad():
            sources = apply_model(self.model, wav, device=self.device, progress=True)
        
        sources = sources[0]  # Enlever batch
        results = {}
        
        # Sauvegarder chaque stem avec soundfile
        for i, name in enumerate(self.model_config["names"]):
            f = out / f"{name}.wav"
            audio_np = sources[i].cpu().numpy().T  # (samples, channels)
            sf.write(str(f), audio_np, self.model.samplerate)
            results[name] = str(f)
            logger.info(f"  ✅ {name}.wav")
        
        return results
    
    def unload_model(self):
        if self.model:
            del self.model
            self.model = None
            torch.cuda.empty_cache()
    
    @classmethod
    def get_available_models(cls): 
        return cls.AVAILABLE_MODELS
    
    @classmethod
    def get_model_info(cls, name): 
        return cls.AVAILABLE_MODELS[name]


_loaded_models = {}

def get_separator(model_name: str):
    if model_name not in _loaded_models:
        _loaded_models[model_name] = MusicSeparator(model_name=model_name)
    return _loaded_models[model_name]

def clear_cache():
    global _loaded_models
    for s in _loaded_models.values():
        s.unload_model()
    _loaded_models.clear()