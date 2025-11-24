# Music Split - AI-Powered Audio Source Separation 🎵

> **Production-ready ML inference service** for separating audio tracks into individual stems using state-of-the-art deep learning models.

[![Live Demo](https://img.shields.io/badge/demo-live-success)](https://music-split-frontend.pages.dev/)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

**🚀 [Try it live](https://music-split-frontend.pages.dev/)** | **📖 [Documentation](docs/)**

---

## ✨ Features

- 🎵 **Multi-Stem Separation**: Extract vocals, drums, bass, guitar, piano, and other instruments
- ⚡ **GPU-Accelerated**: Serverless GPU inference on Modal (NVIDIA T4)
- 🌐 **Modern Web UI**: React-based interface deployed on Cloudflare Pages
- 🎯 **Multiple Models**: 
  - `htdemucs_6s`: 6 stems, faster processing (~30s)
  - `htdemucs_ft`: 4 stems, higher quality (~45s)
- 📊 **Production Monitoring**: Prometheus metrics, structured logging
- 🔄 **Async Processing**: Non-blocking API with process pool execution
- 🎬 **YouTube Support**: Direct separation from YouTube URLs

---

## 🏗️ Architecture

```
┌─────────────────┐
│  Cloudflare     │
│  Pages (CDN)    │  React Frontend
└────────┬────────┘
         │ HTTPS
         ▼
┌─────────────────┐
│  Modal.com      │
│  FastAPI (CPU)  │  REST API
└────────┬────────┘
         │ spawn()
         ▼
┌─────────────────┐
│  Modal.com      │
│  GPU Worker     │  Demucs Inference (T4 GPU)
│  (Serverless)   │  Auto-scales to zero
└─────────────────┘
```

**Key Design Decisions:**
- **Serverless GPU**: Pay-per-use, auto-scaling, no idle costs
- **Separation of Concerns**: API (CPU) handles requests, workers (GPU) process audio
- **Edge Delivery**: Frontend served via Cloudflare's global CDN
- **Async Execution**: Process pool for local dev, Modal functions for production

---

## � Performance

| Metric | Value |
|--------|-------|
| **Separation Time** | 30-45s (depending on model) |
| **GPU Utilization** | ~80% during inference |
| **Cold Start** | <10s (Modal container warm-up) |
| **API Response Time** | <100ms (job submission) |
| **Concurrent Users** | Auto-scales based on demand |
| **Cost per Separation** | ~$0.01 (T4 GPU @ $0.0006/s) |

---

## 🛠️ Tech Stack

### Backend
- **Python 3.10+** - Core language
- **FastAPI** - High-performance async web framework
- **PyTorch 2.8** - Deep learning framework
- **Demucs 4.0** - State-of-the-art source separation (Meta Research)
- **Modal** - Serverless GPU infrastructure

### Frontend
- **React 18** - UI framework
- **Vite** - Build tool
- **Tailwind CSS** - Styling

### Infrastructure
- **Modal** - Serverless compute with GPU
- **Cloudflare Pages** - Static site hosting with global CDN
- **Prometheus** - Metrics collection
- **Docker** - Containerization for local development

---

## 🚀 Quick Start

### Try the Live Demo
Visit **[music-split-frontend.pages.dev](https://music-split-frontend.pages.dev/)** to try it immediately!

### Local Development

1. **Clone the repository:**
```bash
git clone https://github.com/Zbehel/Music_Split/
cd Music_Split
```

2. **Set up Python environment:**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Run the API:**
```bash
uvicorn src.api:app --reload
```

4. **Access the API:**
- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

---

## 📡 API Usage

### Separate Audio File
```bash
curl -X POST "https://zbehel--music-split-api-fastapi-app.modal.run/separate" \
  -F "file=@song.mp3" \
  -F "model_name=htdemucs_6s"
```

### Separate from YouTube
```bash
curl -X POST "https://zbehel--music-split-api-fastapi-app.modal.run/separate/youtube" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/watch?v=...", "model_name": "htdemucs_6s"}'
```

### Check Job Status
```bash
curl "https://zbehel--music-split-api-fastapi-app.modal.run/status/{job_id}"
```

---

## 📊 Monitoring & Observability

The service includes production-grade monitoring:

- **Prometheus Metrics**: Request latency, separation duration, GPU utilization
- **Structured Logging**: JSON logs with request IDs and trace IDs
- **Health Checks**: `/health` endpoint with system status
- **Error Tracking**: Comprehensive error handling with circuit breakers

**Available Metrics:**
- `http_request_duration_seconds` - API response times
- `separation_duration_seconds` - Model inference times
- `separation_file_size_bytes` - Input file sizes
- `models_loaded` - Cached models in memory

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test suite
pytest tests/test_api.py -v
```

**Test Coverage:**
- ✅ API endpoints (FastAPI)
- ✅ Audio separation logic (Demucs)
- ✅ Model loading and caching
- ✅ Error handling and resilience
- ✅ Rate limiting and circuit breakers

---

## 📁 Project Structure

```
Music_Split/
├── src/                    # Backend source code
│   ├── api.py             # FastAPI application
│   ├── separator.py       # Demucs separation logic
│   ├── metrics.py         # Prometheus metrics
│   └── logging_config.py  # Structured logging
├── web/                    # React frontend
│   ├── src/
│   │   ├── App.jsx        # Main component
│   │   └── useAudioSync.js # Audio playback sync
│   └── package.json
├── deploy/
│   ├── modal/             # Modal deployment (GPU backend)
│   │   └── modal_app.py   # Serverless configuration
│   └── cloudflare/        # Cloudflare Pages deployment
│       └── deploy.sh
├── tests/                 # Comprehensive test suite
├── docs/                  # Documentation
└── requirements.txt       # Python dependencies
```

---

## 🚀 Deployment

### Production Architecture

- **Backend**: Deployed on [Modal](https://modal.com) with T4 GPU acceleration
  - Auto-scales based on demand
  - Pay-per-use pricing (~$0.01/separation)
  - Cold start < 10s

- **Frontend**: Deployed on [Cloudflare Pages](https://pages.cloudflare.com)
  - Global CDN distribution
  - Automatic HTTPS
  - Zero-downtime deployments

### Deploy Your Own

1. **Deploy Backend to Modal:**
```bash
modal deploy deploy/modal/modal_app.py
```

2. **Deploy Frontend to Cloudflare:**
```bash
cd web
npm run build
npx wrangler pages deploy dist
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed instructions.

---

## 🎯 Technical Highlights

### MLOps & Production ML
- **Model Serving**: Efficient inference pipeline with PyTorch
- **GPU Optimization**: Serverless GPU with automatic scaling
- **Cost Efficiency**: Pay-per-use model, ~$0.01 per separation
- **Monitoring**: Prometheus metrics for model performance tracking
- **Resilience**: Circuit breakers, rate limiting, retry logic

### Software Engineering
- **Clean Architecture**: Separation of API, business logic, and infrastructure
- **Async Processing**: Non-blocking API with background workers
- **Type Safety**: Full type hints with Pydantic models
- **Testing**: 77+ tests with pytest
- **Documentation**: OpenAPI/Swagger auto-generated docs

### DevOps
- **Serverless Deployment**: Modal for GPU, Cloudflare for frontend
- **CI/CD Ready**: Automated testing and deployment
- **Containerization**: Docker support for local development
- **Observability**: Structured logging, metrics, health checks

---

## 🔧 Technical Challenges Solved

1. **Serverless GPU Inference**: Implemented efficient cold-start optimization and model caching
2. **Async Task Management**: Built process pool executor for local dev, Modal functions for production
3. **Audio Streaming**: Handled large audio files with chunked uploads and streaming responses
4. **Frontend-Backend Sync**: Real-time job status polling with optimistic UI updates
5. **Cost Optimization**: Serverless architecture reduces idle costs to zero

---

## 📚 Documentation

- [Deployment Guide](docs/DEPLOYMENT.md) - Deploy to Modal, Cloud Run, or GKE
- [API Documentation](https://zbehel--music-split-api-fastapi-app.modal.run/docs) - Interactive Swagger UI
- [Architecture](docs/technologies/Backend.md) - Technical deep dive

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## 📄 License

This project is open source and available under the MIT License.

---

## 🙏 Acknowledgments

- **Demucs** by Meta Research - State-of-the-art source separation model
- **Modal** - Serverless GPU infrastructure
- **Cloudflare** - Global CDN and edge computing

---

**Built with ❤️ for music producers, audio engineers, and ML enthusiasts**
