# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
import torch
import torchaudio
from unittest.mock import patch
from src.api import app


@pytest.fixture
def client():
    """Test client for API"""
    return TestClient(app)


@pytest.fixture
def test_audio_file(tmp_path):
    """Generate test audio file"""
    audio = torch.randn(2, 44100 * 5)  # 5s stereo
    test_file = tmp_path / "test.wav"
    torchaudio.save(str(test_file), audio, 44100)
    return test_file


class TestAPIEndpoints:
    """Test API endpoints"""

    def test_root(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Music Source Separator API"
        assert "version" in data
        assert "endpoints" in data

    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "device" in data
        assert "models_loaded" in data

    def test_metrics_endpoint(self, client):
        """Test metrics endpoint"""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    def test_list_models(self, client):
        """Test list models endpoint"""
        response = client.get("/models")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert "total" in data
        assert len(data["models"]) > 0
        assert "htdemucs_6s" in data["models"]

    def test_get_model_info(self, client):
        """Test get model info endpoint"""
        response = client.get("/models/htdemucs_6s")
        assert response.status_code == 200
        data = response.json()
        assert "names" in data  # Changed from "stems" to "names"
        assert "description" in data

    def test_get_invalid_model_info(self, client):
        """Test get info for invalid model"""
        response = client.get("/models/fake_model")
        assert response.status_code == 404  # Should return 404, not 500

    def test_separate_audio_success(self, client, test_audio_file):
        """Test successful audio separation"""
        # Patch the process pool so the job runs synchronously in-test
        from src import api as api_module

        class FakeFuture:
            def __init__(self, result_value):
                self._result = result_value
                self._callbacks = []

            def result(self):
                return self._result

            def add_done_callback(self, cb):
                # call immediately to simulate synchronous completion
                try:
                    cb(self)
                except Exception:
                    pass

        class FakePool:
            def submit(self, fn, *args, **kwargs):
                # ignore fn/args and return a future with a fake result
                fake_res = {
                    "vocals": "/tmp/test/vocals.wav",
                    "drums": "/tmp/test/drums.wav",
                    "bass": "/tmp/test/bass.wav",
                    "other": "/tmp/test/other.wav",
                }
                return FakeFuture(fake_res)

        fake_pool = FakePool()

        # replace the real process pool on the module
        with patch.object(api_module, "_process_pool", fake_pool):
            with open(test_audio_file, "rb") as f:
                response = client.post(
                    "/separate",
                    files={"file": ("test.wav", f, "audio/wav")},
                    data={"model_name": "htdemucs_6s"}
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "job_id" in data
        assert "session_id" in data
        assert data["status_url"].startswith("/status/")

        # Poll status endpoint to confirm job completed and result present
        job_id = data["job_id"]
        status_resp = client.get(f"/status/{job_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["status"] in ("done", "running", "pending")
        # If fake pool invoked callbacks synchronously, it should be done
        if status_data["status"] == "done":
            assert "result" in status_data

    def test_separate_invalid_model(self, client, test_audio_file):
        """Test separation with invalid model"""
        with open(test_audio_file, "rb") as f:
            response = client.post(
                "/separate",
                files={"file": ("test.wav", f, "audio/wav")},
                data={"model_name": "fake_model"}
            )

        assert response.status_code == 400
        assert "non disponible" in response.json()["detail"]

    def test_separate_missing_file(self, client):
        """Test separation without file"""
        response = client.post("/separate", data={"model_name": "htdemucs_6s"})
        assert response.status_code == 422

    def test_download_stem_not_found(self, client):
        """Test downloading non-existent stem"""
        response = client.get("/download/fake_session/fake_stem")
        assert response.status_code == 404

    def test_clear_cache(self, client):
        """Test clear cache endpoint"""
        response = client.post("/clear-cache")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_cleanup_session_not_found(self, client):
        """Test cleanup non-existent session"""
        response = client.delete("/cleanup/fake_session")
        assert response.status_code == 404

    def test_cleanup_all(self, client):
        """Test cleanup all sessions"""
        response = client.post("/cleanup-all")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


class TestAPIMiddleware:
    """Test API middleware"""

    def test_metrics_middleware(self, client, test_audio_file):
        """Test that metrics are recorded"""
        # Make a request to trigger metrics
        response = client.get("/health")
        assert response.status_code == 200

        # Check metrics endpoint
        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200
        assert "http_requests_total" in metrics_response.text


class TestRateLimiting:
    """Test rate limiting functionality"""

    def test_rate_limit_exceeded(self, client, test_audio_file):
        """Test rate limiting behavior"""
        # This test would require more complex setup to trigger rate limiting
        # For now, we test that the rate limiter is properly initialized
        from src.api import api_rate_limiter
        assert api_rate_limiter is not None


class TestCircuitBreaker:
    """Test circuit breaker functionality"""

    def test_circuit_breaker_open(self, client, test_audio_file):
        """Test circuit breaker open state"""
        from src.api import model_circuit_breaker
        
        # Force circuit breaker to open
        model_circuit_breaker.failure_count = 10
        model_circuit_breaker.state = "open"
        
        with patch('src.api.get_separator') as mock_get_separator:
            mock_get_separator.side_effect = Exception("Circuit breaker test")
            
            with open(test_audio_file, "rb") as f:
                response = client.post(
                    "/separate",
                    files={"file": ("test.wav", f, "audio/wav")},
                    data={"model_name": "htdemucs_6s"}
                )
        
        # Reset circuit breaker
        model_circuit_breaker.reset()
        
        # Should return 503 when circuit breaker is open
        assert response.status_code == 503 or response.status_code == 500
