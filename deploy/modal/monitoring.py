import modal
import os
import subprocess
import time
import shutil
from pathlib import Path

# Define volumes for persistence
prom_volume = modal.Volume.from_name("music-split-prometheus-data", create_if_missing=True)
grafana_volume = modal.Volume.from_name("music-split-grafana-data", create_if_missing=True)

# -----------------------------------------------------------------------------
# PROMETHEUS
# -----------------------------------------------------------------------------
prom_image = (
    modal.Image.from_registry("prom/prometheus:v2.45.0")
    .pip_install("fastapi", "uvicorn", "httpx")
    .add_local_file("deploy/monitoring/prometheus.yml", "/etc/prometheus/prometheus.yml")
)

prom_app = modal.App("music-split-monitoring-prometheus", image=prom_image)

@prom_app.function(
    image=prom_image,
    volumes={"/prometheus": prom_volume},
    timeout=3600, # 1 hour (Modal functions have time limits, for perm hosting this needs a loop or "serve")
    allow_concurrent_inputs=100,
)
@modal.asgi_app()
def prometheus_ui():
    import fastapi
    import httpx
    from fastapi import Request, Response
    from fastapi.responses import StreamingResponse

    # Start Prometheus in background if not running
    # Note: In Modal asgi_app, the container might be reused.
    # We check if process is running.
    
    # We need to run prometheus pointing to the config and data dir
    # The image has prometheus at /bin/prometheus
    
    cmd = [
        "/bin/prometheus",
        "--config.file=/etc/prometheus/prometheus.yml",
        "--storage.tsdb.path=/prometheus",
        "--web.listen-address=127.0.0.1:9090",
        "--web.enable-lifecycle"
    ]
    
    # Check if running
    try:
        subprocess.check_output(["pgrep", "prometheus"])
    except subprocess.CalledProcessError:
        print("Starting Prometheus...")
        subprocess.Popen(cmd)
        time.sleep(2) # Wait for startup

    app = fastapi.FastAPI()
    client = httpx.AsyncClient(base_url="http://127.0.0.1:9090")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
    async def proxy(request: Request, path: str):
        url = httpx.URL(path=path, query=request.url.query.encode("utf-8"))
        
        # Stream the request body
        content = request.stream()
        
        req = client.build_request(
            request.method,
            url,
            headers=request.headers.raw,
            content=content
        )
        
        r = await client.send(req, stream=True)
        
        return StreamingResponse(
            r.aiter_raw(),
            status_code=r.status_code,
            headers=r.headers,
            background=None
        )

    return app

# -----------------------------------------------------------------------------
# GRAFANA
# -----------------------------------------------------------------------------
grafana_image = (
    modal.Image.from_registry("grafana/grafana:10.0.0")
    .user("root") # Switch to root to install python/pip
    .apt_install("python3", "python3-pip")
    .pip_install("fastapi", "uvicorn", "httpx")
    # Switch back to grafana user if needed, but root is easier for permission on volumes
    # Add Grafana config if needed, e.g.:
    # .add_local_dir("deploy/monitoring/grafana", "/etc/grafana")
)

grafana_app = modal.App("music-split-monitoring-grafana", image=grafana_image)

@grafana_app.function(
    image=grafana_image,
    volumes={"/var/lib/grafana": grafana_volume},
    timeout=3600,
    allow_concurrent_inputs=100,
)
@modal.asgi_app()
def grafana_ui():
    import fastapi
    import httpx
    from fastapi import Request
    from fastapi.responses import StreamingResponse

    # Start Grafana
    # Grafana usually runs at /usr/share/grafana
    # Binary: /usr/sbin/grafana-server or similar
    
    # We need to ensure permissions on /var/lib/grafana
    # Since we are root (from image definition), it should be fine.
    
    cmd = [
        "grafana-server",
        "--homepath=/usr/share/grafana",
        "--config=/etc/grafana/grafana.ini",
        "cfg:default.paths.data=/var/lib/grafana",
        "cfg:default.server.http_addr=127.0.0.1",
        "cfg:default.server.http_port=3000"
    ]
    
    try:
        subprocess.check_output(["pgrep", "-f", "grafana-server"])
    except subprocess.CalledProcessError:
        print("Starting Grafana...")
        # Grafana might need some env vars or working dir
        subprocess.Popen(cmd, cwd="/usr/share/grafana")
        time.sleep(5)

    app = fastapi.FastAPI()
    client = httpx.AsyncClient(base_url="http://127.0.0.1:3000")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
    async def proxy(request: Request, path: str):
        url = httpx.URL(path=path, query=request.url.query.encode("utf-8"))
        content = request.stream()
        req = client.build_request(
            request.method,
            url,
            headers=request.headers.raw,
            content=content
        )
        r = await client.send(req, stream=True)
        return StreamingResponse(
            r.aiter_raw(),
            status_code=r.status_code,
            headers=r.headers
        )

    return app
