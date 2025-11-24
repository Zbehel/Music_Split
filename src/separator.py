"""Music Source Separator - Sans TorchCodec/FFmpeg"""
from src.stems import STEM_CONFIGS, get_stems, get_num_stems

import torch
import numpy as np
from pathlib import Path
from typing import Dict, Optional, Any, cast
import logging
import soundfile as sf
from demucs.pretrained import get_model
from demucs.apply import apply_model

# CRITICAL: Disable PyTorch's internal multiprocessing to prevent SIGSEGV crashes
# This prevents semaphore leaks and crashes during cleanup after separation
torch.set_num_threads(1)
torch.set_num_interop_threads(1)

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
        # Default to auto-detected best device (CUDA > MPS > CPU) unless overridden
        if device:
            requested = device.lower()
            # Validate requested device availability
            if requested == "cuda" and not torch.cuda.is_available():
                logger.warning("Requested device 'cuda' not available, falling back to best available device")
                self.device = get_best_device()
            elif requested == "mps" and not (hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()):
                logger.warning("Requested device 'mps' not available, falling back to best available device")
                self.device = get_best_device()
            else:
                self.device = requested
        else:
            self.device = get_best_device()
        self.model: Optional[Any] = None
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
        
        # Ensure model is loaded and non-None for type checker
        if self.model is None:
            # Defensive: either load it or raise. Ici on préfère lever une erreur claire.
            raise RuntimeError("Model not loaded. Call _load_model() or use separate() which loads model.")
        model = self.model  # type: ignore[assignment]
        
        # Resample si nécessaire
        if sr != model.samplerate:
            # Resample simple sans torchaudio
            import scipy.signal
            num_samples = int(wav.shape[1] * model.samplerate / sr)
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
            sources = apply_model(model, wav, device=self.device, progress=True)
        
        sources = sources[0]  # Enlever batch
        results = {}
        
        logger.info(f"📝 Starting to write {len(self.model_config['names'])} stems to disk...")
        
        # Process and write stems ONE AT A TIME to minimize VRAM usage
        for i, name in enumerate(self.model_config["names"]):
            logger.info(f"🔄 Processing stem {i+1}/{len(self.model_config['names'])}: {name}")
            
            # Use FLAC instead of OGG - more stable for large files, still compressed
            f = out / f"{name}.flac"
            
            # Extract single stem and immediately move to CPU to free VRAM
            if self.device == "cuda":
                torch.cuda.synchronize()
                logger.debug(f"  ✓ GPU synchronized for {name}")
            
            # Get this stem, move to CPU, and convert to numpy
            logger.debug(f"  → Moving {name} tensor to CPU...")
            stem_tensor = sources[i]
            audio_np = stem_tensor.cpu().numpy().T  # (samples, channels)
            logger.debug(f"  ✓ {name} converted to numpy: shape={audio_np.shape}")
            
            # Immediately delete the GPU tensor to free VRAM
            del stem_tensor
            if self.device == "cuda":
                torch.cuda.empty_cache()
            
            # Write to disk using FLAC (stable, lossless, ~50% compression)
            logger.info(f"  💾 Writing {name}.flac to disk...")
            try:
                sf.write(str(f), audio_np, self.model.samplerate, format='FLAC', subtype='PCM_24')
                file_size_mb = f.stat().st_size / (1024 * 1024)
                logger.info(f"  ✅ {name}.flac written successfully ({file_size_mb:.2f} MB)")
                results[name] = str(f)
            except Exception as e:
                logger.error(f"  ❌ FAILED to write {name}.flac: {e}", exc_info=True)
                raise
            
            # Clean up numpy array
            del audio_np
            logger.debug(f"  ✓ {name} numpy array freed")
        
        logger.info("✅ All stems written successfully")
        
        # Clean up the entire sources tensor
        del sources
        if self.device == "cuda":
            torch.cuda.empty_cache()
        
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
        """Get model information safely"""
        if name not in cls.AVAILABLE_MODELS:
            raise ValueError(f"Model '{name}' not found")
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