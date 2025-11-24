# Backend Technologies

This document outlines the core technologies used in the backend of the Music Split application.

## 🐍 Python & FastAPI
The backend is built using **Python 3.10+** and **FastAPI**.
*   **FastAPI**: A modern, fast (high-performance) web framework for building APIs with Python 3.6+ based on standard Python type hints. It provides automatic OpenAPI documentation (Swagger UI).
*   **Uvicorn**: An ASGI web server implementation for Python, used to run the FastAPI application.

## 🧠 AI & Machine Learning
The core functionality of music separation is powered by deep learning models.
*   **PyTorch**: The open-source machine learning framework used to run the separation models.
*   **Demucs**: A state-of-the-art music source separation model architecture developed by Meta Research. We specifically use the Hybrid Transformer Demucs (htdemucs) models.
*   **Audio Separator**: A Python package that provides an easy-to-use interface for running Demucs and other separation models.

## 🎵 Audio Processing
*   **FFmpeg**: A complete, cross-platform solution to record, convert and stream audio and video. It is used for audio format conversion and processing.
*   **yt-dlp**: A command-line program to download videos from YouTube.com and other video sites. It is used to fetch audio from YouTube links provided by the user.

## ⚡ Asynchronous Processing
