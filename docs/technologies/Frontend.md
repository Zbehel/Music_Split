# Frontend Technologies

This document outlines the core technologies used in the frontend of the Music Split application.

## ⚛️ React Ecosystem
The frontend is a Single Page Application (SPA) built with **React**.
*   **React**: A JavaScript library for building user interfaces. We use functional components and Hooks.
*   **Vite**: A build tool that aims to provide a faster and leaner development experience for modern web projects. It serves as our development server and bundler.

## 🎨 Styling & UI
*   **Tailwind CSS**: A utility-first CSS framework packed with classes like `flex`, `pt-4`, `text-center` and `rotate-90` that can be composed to build any design, directly in your markup.
*   **Lucide React**: A collection of beautiful, consistent icons used throughout the application interface.

## 📡 State & Data Fetching
*   **Axios**: A promise-based HTTP client for the browser and node.js. It is used to communicate with the backend API (uploading files, checking status, downloading stems).

## 🔊 Audio Visualization
*   **Web Audio API**: Native browser API used for controlling audio on the Web.
*   **Canvas API**: Used in conjunction with the Web Audio API to render the real-time frequency spectrum visualizer (`Spectrum.jsx`).
