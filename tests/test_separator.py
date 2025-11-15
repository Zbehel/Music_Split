import pytest
import torch
import torchaudio
from pathlib import Path
from src import MusicSeparator, ModelConfig, list_available_models


@pytest.fixture
def test_audio(tmp_path):
    """Generate test audio file"""
    audio = torch.randn(2, 44100 * 10)  # 10s stereo
    test_file = tmp_path / "test.wav"
    torchaudio.save(str(test_file), audio, 44100, backend="soundfile")
    return test_file


class TestModelConfig:
    """Test ModelConfig class"""

    def test_list_available_models(self):
        """Test that we can list available models"""
        models = ModelConfig.list_available_models()
        assert isinstance(models, list)
        assert len(models) > 0
        assert "htdemucs" in models
        assert "htdemucs_6s" in models

    def test_get_stems_4stem_model(self):
        """Test getting stems for 4-stem model"""
        stems = ModelConfig.get_stems("htdemucs")
        assert len(stems) == 4
        assert set(stems) == {"drums", "bass", "other", "vocals"}

    def test_get_stems_6stem_model(self):
        """Test getting stems for 6-stem model"""
        stems = ModelConfig.get_stems("htdemucs_6s")
        assert len(stems) == 6
        assert set(stems) == {"drums", "bass", "other", "vocals", "guitar", "piano"}

    def test_is_supported(self):
        """Test model support checking"""
        assert ModelConfig.is_supported("htdemucs") is True
        assert ModelConfig.is_supported("htdemucs_6s") is True
        assert ModelConfig.is_supported("fake_model") is False


class TestMusicSeparator:
    """Test MusicSeparator class"""

    def test_separator_initialization(self):
        """Test separator can be initialized"""
        separator = MusicSeparator(model_name="htdemucs")
        assert separator.device in ["cuda", "cpu", "mps"]
        assert separator.model_name == "htdemucs"
        assert len(separator.stems) == 4

    def test_separator_4stem_model(self):
        """Test 4-stem model initialization"""
        separator = MusicSeparator(model_name="htdemucs")
        assert separator.model_name == "htdemucs"
        assert len(separator.stems) == 4
        expected_stems = {"drums", "bass", "other", "vocals"}
        assert set(separator.stems) == expected_stems

    def test_separator_6stem_model(self):
        """Test 6-stem model initialization"""
        separator = MusicSeparator(model_name="htdemucs_6s")
        assert separator.model_name == "htdemucs_6s"
        assert len(separator.stems) == 6
        expected_stems = {"drums", "bass", "other", "vocals", "guitar", "piano"}
        assert set(separator.stems) == expected_stems

    def test_separator_info_property(self):
        """Test info property returns correct data"""
        separator = MusicSeparator(model_name="htdemucs")
        info = separator.info

        assert "model_name" in info
        assert "device" in info
        assert "stems" in info
        assert "num_stems" in info
        assert "sample_rate" in info

        assert info["model_name"] == "htdemucs"
        assert info["num_stems"] == 4
        assert info["sample_rate"] == 44100

    def test_device_auto_detection(self):
        """Test automatic device detection"""
        separator = MusicSeparator(model_name="htdemucs", device="auto")
        assert separator.device in ["cuda", "cpu", "mps"]

    def test_separation_4stem(self, test_audio, tmp_path):
        """Test separation with 4-stem model"""
        separator = MusicSeparator(model_name="htdemucs")
        output_dir = tmp_path / "output_4stem"

        results = separator.separate(str(test_audio), str(output_dir))

        # Verify results
        assert len(results) == 4
        for stem in ["vocals", "drums", "bass", "other"]:
            assert stem in results
            assert Path(results[stem]).exists()

            # Verify audio file is valid
            wav, sr = torchaudio.load(results[stem])
            assert wav.shape[0] == 2  # Stereo
            assert sr == 44100

    def test_separation_6stem(self, test_audio, tmp_path):
        """Test separation with 6-stem model"""
        separator = MusicSeparator(model_name="htdemucs_6s")
        output_dir = tmp_path / "output_6stem"

        results = separator.separate(str(test_audio), str(output_dir))

        # Verify results
        assert len(results) == 6
        for stem in ["vocals", "drums", "bass", "other", "guitar", "piano"]:
            assert stem in results
            assert Path(results[stem]).exists()

            # Verify audio file is valid
            wav, sr = torchaudio.load(results[stem])
            assert wav.shape[0] == 2  # Stereo
            assert sr == 44100

    def test_separation_different_formats(self, test_audio, tmp_path):
        """Test separation with different output formats"""
        separator = MusicSeparator(model_name="htdemucs")

        for fmt in ["wav", "flac"]:  # mp3 needs additional dependencies
            output_dir = tmp_path / f"output_{fmt}"
            results = separator.separate(
                str(test_audio), str(output_dir), save_format=fmt
            )

            for stem_path in results.values():
                assert Path(stem_path).suffix == f".{fmt}"
                assert Path(stem_path).exists()

    def test_separation_mono_input(self, tmp_path):
        """Test separation handles mono input correctly"""
        # Create mono audio
        audio = torch.randn(1, 44100 * 5)  # 5s mono
        test_file = tmp_path / "test_mono.wav"
        torchaudio.save(str(test_file), audio, 44100, backend="soundfile")

        separator = MusicSeparator(model_name="htdemucs")
        output_dir = tmp_path / "output_mono"

        results = separator.separate(str(test_file), str(output_dir))

        # Should still output stereo
        for stem_path in results.values():
            wav, sr = torchaudio.load(stem_path)
            assert wav.shape[0] == 2  # Converted to stereo

    def test_separation_different_sample_rate(self, tmp_path):
        """Test separation handles different sample rates"""
        # Create audio with different sample rate
        audio = torch.randn(2, 48000 * 5)  # 5s @ 48kHz
        test_file = tmp_path / "test_48k.wav"
        torchaudio.save(str(test_file), audio, 48000, backend="soundfile")

        separator = MusicSeparator(model_name="htdemucs")
        output_dir = tmp_path / "output_48k"

        results = separator.separate(str(test_file), str(output_dir))

        # Should be resampled to 44.1kHz
        for stem_path in results.values():
            wav, sr = torchaudio.load(stem_path)
            assert sr == 44100


class TestHelperFunctions:
    """Test helper functions"""

    def test_list_available_models_function(self):
        """Test list_available_models helper function"""
        models = list_available_models()
        assert isinstance(models, list)
        assert len(models) > 0
        assert "htdemucs" in models


@pytest.mark.parametrize(
    "model_name",
    [
        "htdemucs",
        "htdemucs_ft",
        "htdemucs_6s",
    ],
)
def test_all_models(model_name, test_audio, tmp_path):
    """Parametrized test for all available models"""
    separator = MusicSeparator(model_name=model_name)
    output_dir = tmp_path / f"output_{model_name}"

    results = separator.separate(str(test_audio), str(output_dir))

    # Verify all stems are present
    assert len(results) == len(separator.stems)

    for stem in separator.stems:
        assert stem in results
        assert Path(results[stem]).exists()
