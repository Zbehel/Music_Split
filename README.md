# Music Split - Source Separation Service

A FastAPI-based service for separating audio tracks into individual stems (vocals, drums, bass, other) using the Demucs deep learning model.

## Features

- 🎵 **Audio Source Separation**: Separate music into 4 stems (vocals, drums, bass, other)
- 🚀 **FastAPI REST API**: Easy-to-use HTTP API for audio processing
- 🐳 **Docker Support**: Containerized deployment
- ☸️ **Kubernetes Ready**: Full K8s deployment configurations
- 🧪 **Tested**: Unit tests with pytest
- 📊 **Benchmarking**: Performance benchmarking tools

## Tech Stack

- **Python 3.11+**
- **FastAPI**: Web framework
- **Demucs**: Source separation model
- **PyTorch**: Deep learning framework
- **Docker**: Containerization
- **Kubernetes**: Orchestration

## Installation

### Local Development

1. Clone the repository:
```bash
git clone <repository-url>
cd Music_Split
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the API:
```bash
uvicorn src.api:app --reload
```

The API will be available at `http://localhost:8000`

## Usage

### API Endpoints

- `GET /health`: Health check endpoint
- `POST /separate`: Upload an audio file and get separated stems
- `GET /docs`: Interactive API documentation (Swagger UI)

### Example: Separate Audio

```bash
curl -X POST "http://localhost:8000/separate" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_audio.mp3"
```

### Using the Python Client

```python
from src import MusicSeparator

separator = MusicSeparator()
results = separator.separate("input.mp3", "output_dir")
# Returns: {'vocals': 'path/to/vocals.wav', 'drums': '...', ...}
```

## Docker

### Build the image:
```bash
docker build -t music-separator:latest .
```

### Run with Docker:
```bash
docker run -p 8000:8000 music-separator:latest
```

### Docker Compose:
```bash
docker-compose up
```

## Kubernetes

### Prerequisites
- Minikube or Kubernetes cluster
- kubectl configured

### Deploy:
```bash
# Create namespace
kubectl apply -f k8s/namespace.yaml

# Deploy application
kubectl apply -f k8s/deployment.yaml

# Port forward to access the service
kubectl port-forward svc/music-separator-service 8000:80 -n music-separation
```

## Testing

Run tests with pytest:
```bash
pytest tests/ -v
```

## Benchmarking

Run performance benchmarks:
```bash
python benchmark.py
```

## Project Structure

```
Music_Split/
├── src/
│   ├── __init__.py
│   ├── api.py          # FastAPI application
│   ├── separator.py    # Music separation logic
│   └── config.py       # Configuration
├── tests/
│   └── test_separator.py
├── k8s/
│   ├── deployment.yaml
│   └── namespace.yaml
├── dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Requirements

- Python 3.11+
- NumPy < 2.0 (compatibility with PyTorch 2.2.2)
- PyTorch 2.2.2+
- Demucs 4.0.1

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

