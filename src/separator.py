import torch
import torchaudio
from pathlib import Path
from typing import Dict, List, Optional
from demucs.pretrained import get_model
from demucs.apply import apply_model


class ModelConfig:
    """Configuration for different separation models"""

    # Mapping des modèles Demucs et leurs stems
    DEMUCS_MODELS = {
        "htdemucs": ["drums", "bass", "other", "vocals"],
        "htdemucs_ft": ["drums", "bass", "other", "vocals"],
        "htdemucs_6s": ["drums", "bass", "other", "vocals", "guitar", "piano"],
        "hdemucs_mmi": ["drums", "bass", "other", "vocals"],
        "mdx": ["drums", "bass", "other", "vocals"],
        "mdx_extra": ["drums", "bass", "other", "vocals"],
        "mdx_q": ["drums", "bass", "other", "vocals"],
        "mdx_extra_q": ["drums", "bass", "other", "vocals"],
    }

    @classmethod
    def get_stems(cls, model_name: str) -> List[str]:
        """Get stem names for a given model"""
        # Pour les modèles Demucs
        if model_name in cls.DEMUCS_MODELS:
            return cls.DEMUCS_MODELS[model_name]

        # Fallback par défaut (4 stems)
        return ["drums", "bass", "other", "vocals"]

    @classmethod
    def is_supported(cls, model_name: str) -> bool:
        """Check if model is supported"""
        return model_name in cls.DEMUCS_MODELS

    @classmethod
    def list_available_models(cls) -> List[str]:
        """List all available models"""
        return list(cls.DEMUCS_MODELS.keys())


class MusicSeparator:
    """
    Generic music source separation class.
    Supports multiple Demucs models with automatic stem detection.
    """

    def __init__(self, model_name: str = "htdemucs", device: str = "auto"):
        """
        Initialize the music separator

        Args:
            model_name: Name of the model to use
            device: Device to run on ('auto', 'cuda', 'cpu', 'mps')
        """
        self.model_name = model_name

        # Auto-detect device
        if device == "auto":
            self.device = self._detect_device()
        else:
            self.device = device

        # Get stems for this model
        self.stems = ModelConfig.get_stems(model_name)

        print(f"Loading model '{model_name}' on {self.device}...")
        print(f"Stems: {', '.join(self.stems)}")

        # Load model
        self.model = get_model(model_name)
        self.model.to(self.device)
        self.model.eval()

        self.sample_rate = 44100

    def _detect_device(self) -> str:
        """Auto-detect best available device"""
        if torch.cuda.is_available():
            return "cuda"
        elif torch.backends.mps.is_available():
            return "mps"
        else:
            return "cpu"

    def separate(
        self, audio_path: str, output_dir: str = "output", save_format: str = "wav"
    ) -> Dict[str, str]:
        """
        Separate audio into stems

        Args:
            audio_path: Path to input audio file
            output_dir: Directory to save separated stems
            save_format: Output format (wav, mp3, flac)

        Returns:
            Dictionary mapping stem names to output file paths
        """
        # Load audio
        wav, sr = torchaudio.load(audio_path)

        # Resample if needed
        if sr != self.sample_rate:
            resampler = torchaudio.transforms.Resample(sr, self.sample_rate)
            wav = resampler(wav)
            sr = self.sample_rate

        # Ensure stereo
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        elif wav.shape[0] > 2:
            wav = wav[:2]  # Keep only first 2 channels

        # Move to device
        wav = wav.to(self.device)

        # Separate
        with torch.no_grad():
            sources = apply_model(self.model, wav[None], split=True, device=self.device)

        sources = sources[0]  # Remove batch dimension: [n_stems, 2, samples]

        # Validate number of stems
        if sources.shape[0] != len(self.stems):
            raise ValueError(
                f"Model returned {sources.shape[0]} stems but expected {len(self.stems)}"
            )

        # Save stems
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True, parents=True)

        results = {}
        for i, stem_name in enumerate(self.stems):
            stem_audio = sources[i].cpu()
            save_path = output_path / f"{stem_name}.{save_format}"
            # Utiliser backend soundfile explicitement pour éviter torchcodec
            torchaudio.save(
                str(save_path), stem_audio, self.sample_rate, backend="soundfile"
            )
            results[stem_name] = str(save_path)
            print(f"✓ Saved: {save_path}")

        return results

    @property
    def info(self) -> Dict:
        """Get separator information"""
        return {
            "model_name": self.model_name,
            "device": self.device,
            "stems": self.stems,
            "num_stems": len(self.stems),
            "sample_rate": self.sample_rate,
        }


def list_available_models() -> List[str]:
    """Helper function to list available models"""
    return ModelConfig.list_available_models()


if __name__ == "__main__":
    # Example usage
    print("Available models:", list_available_models())

    separator = MusicSeparator(model_name="htdemucs")
    print(separator.info)
    # separator.separate("test.mp3", "output")
