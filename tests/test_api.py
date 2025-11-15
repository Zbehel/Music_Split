import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import torch
import torchaudio
from src.api import app, RESULTS_DIR


@pytest.fixture
def client():
    """Test client for API"""
    return TestClient(app)


@pytest.fixture
def test_audio_file(tmp_path):
    """Generate test audio file"""
    audio = torch.randn(2, 44100 * 10)  # 10s stereo
    test_file = tmp_path / "test.wav"
    torchaudio.save(str(test_file), audio, 44100, backend="soundfile")
    return test_file


class TestAPIEndpoints:
    """Test API endpoints"""

    def test_root(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data

    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "device" in data
        assert "default_model" in data

    def test_list_models(self, client):
        """Test list models endpoint"""
        response = client.get("/models")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert "default" in data
        assert "total" in data
        assert len(data["models"]) > 0
        assert "htdemucs" in data["models"]

    def test_get_model_info(self, client):
        """Test get model info endpoint"""
        response = client.get("/models/htdemucs/info")
        assert response.status_code == 200
        data = response.json()
        assert "model_name" in data
        assert "stems" in data
        assert "num_stems" in data
        assert data["model_name"] == "htdemucs"
        assert data["num_stems"] == 4

    def test_get_invalid_model_info(self, client):
        """Test get info for invalid model"""
        response = client.get("/models/fake_model/info")
        assert response.status_code == 404

    def test_separate_default_model(self, client, test_audio_file):
        """Test separation with default model"""
        with open(test_audio_file, "rb") as f:
            response = client.post(
                "/separate", files={"file": ("test.wav", f, "audio/wav")}
            )

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "completed"
        assert "stems" in data
        assert len(data["stems"]) == 4  # htdemucs default

    def test_separate_with_model_parameter(self, client, test_audio_file):
        """Test separation with specific model"""
        with open(test_audio_file, "rb") as f:
            response = client.post(
                "/separate?model_name=htdemucs_6s",
                files={"file": ("test.wav", f, "audio/wav")},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "htdemucs_6s"
        assert len(data["stems"]) == 6  # 6-stem model

    def test_separate_invalid_model(self, client, test_audio_file):
        """Test separation with invalid model"""
        with open(test_audio_file, "rb") as f:
            response = client.post(
                "/separate?model_name=fake_model",
                files={"file": ("test.wav", f, "audio/wav")},
            )

        assert response.status_code == 400
        assert "Invalid model" in response.json()["detail"]

    def test_get_job_status(self, client, test_audio_file):
        """Test get job status"""
        # First create a job
        with open(test_audio_file, "rb") as f:
            response = client.post(
                "/separate", files={"file": ("test.wav", f, "audio/wav")}
            )

        job_id = response.json()["job_id"]

        # Then check status
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "completed"

    def test_get_nonexistent_job(self, client):
        """Test getting status of nonexistent job"""
        response = client.get("/jobs/fake-job-id")
        assert response.status_code == 404

    def test_download_stem(self, client, test_audio_file):
        """Test downloading a stem"""
        # First create a job
        with open(test_audio_file, "rb") as f:
            response = client.post(
                "/separate", files={"file": ("test.wav", f, "audio/wav")}
            )

        job_id = response.json()["job_id"]
        stems = response.json()["stems"]

        # Download first stem
        stem_url = list(stems.values())[0]
        response = client.get(stem_url)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("audio/")

    def test_delete_job(self, client, test_audio_file):
        """Test deleting a job"""
        # Create a job
        with open(test_audio_file, "rb") as f:
            response = client.post(
                "/separate", files={"file": ("test.wav", f, "audio/wav")}
            )

        job_id = response.json()["job_id"]

        # Delete it
        response = client.delete(f"/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

        # Verify it's gone
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 404


class TestAPIValidation:
    """Test API input validation"""

    def test_missing_file(self, client):
        """Test separation without file"""
        response = client.post("/separate")
        assert response.status_code == 422  # Unprocessable Entity

    def test_output_format_parameter(self, client, test_audio_file):
        """Test different output formats"""
        with open(test_audio_file, "rb") as f:
            response = client.post(
                "/separate?output_format=flac",
                files={"file": ("test.wav", f, "audio/wav")},
            )

        assert response.status_code == 200
        stems = response.json()["stems"]

        # Check that files have correct extension
        for url in stems.values():
            assert ".flac" in url
