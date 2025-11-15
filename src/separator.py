import torch
import torchaudio
from pathlib import Path
from demucs.pretrained import get_model
from demucs.apply import apply_model

class MusicSeparator:
    def __init__(self, model_name='htdemucs_6s', device='auto'):
        if device == 'auto':
            self.device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
        else:
            self.device = device
        
        print(f"Loading model {model_name} on {self.device}...")
        self.model = get_model(model_name)
        self.model.to(self.device)
        self.model.eval()
        
        self.stems = ['drums', 'bass', 'other', 'vocals', 'guitar', 'piano']
    
    def separate(self, audio_path: str, output_dir: str = 'output'):
        """Separate audio into stems"""
        # Load audio
        wav, sr = torchaudio.load(audio_path)
        
        # Resample if needed
        if sr != 44100:
            resampler = torchaudio.transforms.Resample(sr, 44100)
            wav = resampler(wav)
            sr = 44100
        
        # Ensure stereo
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        
        # Move to device
        wav = wav.to(self.device)
        
        # Separate
        with torch.no_grad():
            sources = apply_model(
                self.model, 
                wav[None],
                split=True,
                device=self.device
            )
        
        sources = sources[0]  # [4, 2, samples]
        
        # Save stems
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True, parents=True)
        
        results = {}
        for i, stem_name in enumerate(self.stems):
            stem_audio = sources[i].cpu()
            save_path = output_path / f"{stem_name}.wav"
            torchaudio.save(str(save_path), stem_audio, 44100)
            results[stem_name] = str(save_path)
            print(f"✓ Saved: {save_path}")
        
        return results

if __name__ == "__main__":
    separator = MusicSeparator()
    separator.separate("test.mp3", "output")