import React, { useEffect, useRef } from 'react';

const Spectrum = ({ audioNode, color = '#6366f1' }) => {
    const canvasRef = useRef(null);
    const containerRef = useRef(null);
    const animationRef = useRef(null);
    const audioContextRef = useRef(null);
    const sourceRef = useRef(null);
    const analyzerRef = useRef(null);

    // Handle canvas resizing to match container
    useEffect(() => {
        if (!canvasRef.current || !containerRef.current) return;

        const canvas = canvasRef.current;
        const container = containerRef.current;

        const resizeCanvas = () => {
            const rect = container.getBoundingClientRect();
            const dpr = window.devicePixelRatio || 1;

            // Set canvas resolution to match display size with device pixel ratio
            canvas.width = rect.width * dpr;
            canvas.height = rect.height * dpr;

            // Scale context to account for device pixel ratio
            const ctx = canvas.getContext('2d');
            ctx.scale(dpr, dpr);
        };

        resizeCanvas();

        const resizeObserver = new ResizeObserver(resizeCanvas);
        resizeObserver.observe(container);

        return () => {
            resizeObserver.disconnect();
        };
    }, []);

    useEffect(() => {
        if (!audioNode || !canvasRef.current) return;

        const audio = audioNode;
        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');

        // Initialize Audio Context
        if (!audioContextRef.current) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            audioContextRef.current = new AudioContext();

            analyzerRef.current = audioContextRef.current.createAnalyser();
            analyzerRef.current.fftSize = 256; // Controls resolution (bars count)

            // Connect audio element to analyzer
            try {
                sourceRef.current = audioContextRef.current.createMediaElementSource(audio);
                sourceRef.current.connect(analyzerRef.current);
                analyzerRef.current.connect(audioContextRef.current.destination);
            } catch (e) {
                console.error("Error connecting audio source:", e);
            }
        }

        const bufferLength = analyzerRef.current.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const draw = () => {
            if (!canvas) return;

            const dpr = window.devicePixelRatio || 1;
            const width = canvas.width / dpr;
            const height = canvas.height / dpr;

            animationRef.current = requestAnimationFrame(draw);

            analyzerRef.current.getByteFrequencyData(dataArray);

            ctx.clearRect(0, 0, width, height);

            const barWidth = (width / bufferLength) * 2.5;
            let barHeight;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                barHeight = (dataArray[i] / 255) * height;

                ctx.fillStyle = color;
                // Add some transparency/glow effect
                ctx.globalAlpha = 0.6;
                ctx.fillRect(x, height - barHeight, barWidth, barHeight);

                x += barWidth + 1;
            }
        };

        // Handle audio play/pause to resume context if suspended
        const handlePlay = () => {
            if (audioContextRef.current.state === 'suspended') {
                audioContextRef.current.resume();
            }
            draw();
        };

        const handlePause = () => {
            if (animationRef.current) {
                cancelAnimationFrame(animationRef.current);
            }
        };

        audio.addEventListener('play', handlePlay);
        audio.addEventListener('pause', handlePause);

        // If already playing, start drawing
        if (!audio.paused) {
            handlePlay();
        }

        return () => {
            if (animationRef.current) {
                cancelAnimationFrame(animationRef.current);
            }
            audio.removeEventListener('play', handlePlay);
            audio.removeEventListener('pause', handlePause);
            // Note: We generally don't close the AudioContext here as it might be expensive to recreate,
            // but for this specific component lifecycle it might be okay. 
            // However, to avoid issues with multiple contexts, we'll leave it open or manage it carefully.
        };
    }, [audioNode, color]);

    return (
        <div ref={containerRef} className="w-full h-full">
            <canvas
                ref={canvasRef}
                className="w-full h-full opacity-80"
            />
        </div>
    );
};

export default Spectrum;
