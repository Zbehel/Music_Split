# tests/test_separator.py

import pytest
import torch
import torchaudio
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.separator import MusicSeparator, get_separator, clear_cache, get_best_device
from src.stems import STEM_CONFIGS


@pytest.fixture
def test_audio(tmp_path):
    """Generate test audio file"""
    audio = torch.randn(2, 44100 * 5)  # 5s stereo
    test_file = tmp_path / "test.wav"
    torchaudio.save(str(test_file), audio, 44100)
    return test_file


class TestDeviceDetection:
    """Test device detection functionality"""

    def test_get_best_device_cuda(self):
        """Test CUDA device detection"""
        with patch('torch.cuda.is_available', return_value=True):
            device = get_best_device()
            assert device == "cuda"

    def test_get_best_device_mps(self):
        """Test MPS device detection"""
        with patch('torch.cuda.is_available', return_value=False):
            with patch('torch.backends.mps.is_available', return_value=True):
                device = get_best_device()
                assert device == "mps"

    def test_get_best_device_cpu(self):
        """Test CPU fallback"""
        with patch('torch.cuda.is_available', return_value=False):
            with patch('torch.backends.mps.is_available', return_value=False):
                device = get_best_device()
                assert device == "cpu"


class TestMusicSeparator:
    """Test MusicSeparator class"""

    def test_separator_initialization(self):
        """Test separator can be initialized"""
        separator = MusicSeparator(model_name="htdemucs_6s")
        assert separator.model_name == "htdemucs_6s"
        assert len(separator.stems) == 6
        assert separator.device in ["cuda", "cpu", "mps"]

    def test_separator_invalid_model(self):
        """Test separator with invalid model"""
        with pytest.raises(ValueError):
            MusicSeparator(model_name="fake_model")

    def test_separator_model_info(self):
        """Test model info retrieval"""
        separator = MusicSeparator(model_name="htdemucs_6s")
        info = MusicSeparator.get_model_info("htdemucs_6s")
        assert "names" in info  # Fixed: changed from "stems" to "names"
        assert "description" in info

    def test_load_model(self):
        """Test model loading"""
        separator = MusicSeparator(model_name="htdemucs_6s")
        with patch('src.separator.get_model') as mock_get_model:
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            separator._load_model()
            assert separator.model is not None

    def test_separate_method(self, test_audio, tmp_path):
        """Test separation method"""
        separator = MusicSeparator(model_name="htdemucs_6s")
        
        # Mock the model and apply_model
        with patch('src.separator.get_model') as mock_get_model:
            mock_model = MagicMock()
            mock_model.samplerate = 44100
            mock_get_model.return_value = mock_model
            
            separator.model = mock_model
            
            with patch('src.separator.apply_model') as mock_apply_model:
                # Create mock separated sources
                mock_sources = torch.randn(1, 6, 2, 44100 * 5)  # batch, stems, channels, samples
                mock_apply_model.return_value = mock_sources
                
                output_dir = tmp_path / "output"
                results = separator.separate(str(test_audio), str(output_dir))
                
                assert len(results) == 6
                for stem in ["vocals", "drums", "bass", "other", "guitar", "piano"]:
                    assert stem in results
                    assert Path(results[stem]).exists()


class TestModelCache:
    """Test model caching functionality"""

    def test_get_separator(self):
        """Test get_separator function"""
        # Clear cache first
        clear_cache()
        
        # Get separator
        separator1 = get_separator("htdemucs_6s")
        separator2 = get_separator("htdemucs_6s")
        
        # Should return same instance
        assert separator1 is separator2
        
        # Clear cache
        clear_cache()
        
        # Should create new instance
        separator3 = get_separator("htdemucs_6s")
        assert separator1 is not separator3

    def test_clear_cache(self):
        """Test clear_cache function"""
        # Load a model
        separator = get_separator("htdemucs_6s")
        assert separator is not None
        
        # Clear cache
        clear_cache()
        
        # Import the global cache to check it's empty
        from src.separator import _loaded_models
        assert len(_loaded_models) == 0


class TestSeparatorIntegration:
    """Integration tests for separator"""

    @pytest.mark.parametrize("model_name", ["htdemucs_6s", "htdemucs_ft"])
    def test_available_models(self, model_name):
        """Test that all expected models are available"""
        models = MusicSeparator.get_available_models()
        assert model_name in models
        assert "names" in models[model_name]  # Fixed: changed from "stems" to "names"
        assert "description" in models[model_name]


class TestSeparatorErrorHandling:
    """Test error handling in separator"""

    def test_separate_file_not_found(self, tmp_path):
        """Test separation with non-existent file"""
        separator = MusicSeparator(model_name="htdemucs_6s")
        with pytest.raises(Exception):
            separator.separate("/non/existent/file.wav", str(tmp_path))

    def test_unload_model(self):
        """Test model unloading"""
        separator = MusicSeparator(model_name="htdemucs_6s")
        with patch('src.separator.get_model') as mock_get_model:
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            separator._load_model()
            
            # Mock torch.cuda.empty_cache
            with patch('torch.cuda.empty_cache') as mock_empty_cache:
                separator.unload_model()
                assert separator.model is None
                if torch.cuda.is_available():
                    mock_empty_cache.assert_called_once()
