# Infrastructure & DevOps

This document outlines the infrastructure and DevOps tools used to deploy and manage the Music Split application.

## 🐳 Containerization
*   **Docker**: Used to package both the backend and frontend applications into portable containers. This ensures consistency across development and production environments.
    *   **Backend Dockerfile**: Builds a Python environment with system dependencies (ffmpeg) and installs the application.
    *   **Frontend Dockerfile**: Builds the React app and serves it using a lightweight web server (like nginx or a simple python server, or in our case, Cloud Run's managed environment).

## ☁️ Google Cloud Platform (GCP)
The application is deployed on Google Cloud Platform.

*   **Cloud Run**: A fully managed serverless platform that automatically scales containers.
    *   **Backend Service**: Runs the FastAPI container. It scales down to zero when not in use to save costs.
    *   **Frontend Service**: Runs the React frontend container.
*   **Artifact Registry**: A private Docker registry where our built container images are stored before being deployed to Cloud Run.
*   **Cloud Build**: A serverless CI/CD platform. We use it to automate the build process:
    1.  Build the Docker image.
    2.  Push the image to Artifact Registry.
    3.  Deploy the image to Cloud Run.

## 🚀 Deployment Scripts
We use shell scripts to automate the deployment process:
*   `deploy/cloud-run/deploy.sh`: The main deployment script. It handles:
    *   Enabling required GCP APIs.
    *   Creating the Artifact Registry repository.
    *   Building and deploying the Backend (with GPU support if available).
    *   Building and deploying the Frontend (injecting the Backend API URL).
*   `deploy/cloud-run/deploy-cpu.sh`: A variant of the deployment script configured for CPU-only environments (useful for testing or when GPU quota is unavailable).
