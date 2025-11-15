import pytest
import torch
from src import MusicSeparator
from pathlib import Path

def test_separator_initialization():
    separator = MusicSeparator()
    assert separator.device in ['cuda', 'cpu']
    assert len(separator.stems) == 4

def test_separation(tmp_path):
    # Générer audio test
    import torchaudio
    audio = torch.randn(2, 44100 * 30)  # 30s stereo
    test_file = tmp_path / "test.wav"
    torchaudio.save(str(test_file), audio, 44100)
    
    # Séparer
    separator = MusicSeparator()
    results = separator.separate(str(test_file), str(tmp_path / "output"))
    
    # Vérifier
    assert len(results) == 4
    for stem in ['vocals', 'drums', 'bass', 'other']:
        assert stem in results
        assert Path(results[stem]).exists()