import { useState, useEffect, useRef, useCallback } from 'react';

export function useWebAudio(stems) {
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [volumes, setVolumes] = useState({});
    const [muted, setMuted] = useState({});
    const [isLoading, setIsLoading] = useState(false);
    const [loadingProgress, setLoadingProgress] = useState(0);

    // Audio Context and Nodes
    const audioContextRef = useRef(null);
    const sourceNodesRef = useRef({}); // stem_name -> AudioBufferSourceNode
    const gainNodesRef = useRef({});   // stem_name -> GainNode
    const buffersRef = useRef({});     // stem_name -> AudioBuffer

    // Playback State
    const startTimeRef = useRef(0);    // When playback started (context time)
    const pauseTimeRef = useRef(0);    // Where we paused (offset)
    const rafRef = useRef(null);

    // Initialize Audio Context
    useEffect(() => {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        audioContextRef.current = new AudioContext();

        return () => {
            if (audioContextRef.current) {
                audioContextRef.current.close();
            }
            cancelAnimationFrame(rafRef.current);
        };
    }, []);

    // Load Stems
    useEffect(() => {
        if (!stems || stems.length === 0) return;

        const loadStems = async () => {
            setIsLoading(true);
            setLoadingProgress(0);
            setIsPlaying(false);
            pauseTimeRef.current = 0;

            // Stop any existing playback
            stopAllSources();

            // Reset buffers
            buffersRef.current = {};

            // Initialize volumes/muted state
            const newVolumes = {};
            const newMuted = {};
            stems.forEach(stem => {
                newVolumes[stem.name] = 1.0;
                newMuted[stem.name] = false;
            });
            setVolumes(newVolumes);
            setMuted(newMuted);

            let loadedCount = 0;
            const total = stems.length;

            try {
                await Promise.all(stems.map(async (stem) => {
                    const response = await fetch(stem.url);
                    const arrayBuffer = await response.arrayBuffer();
                    const audioBuffer = await audioContextRef.current.decodeAudioData(arrayBuffer);

                    buffersRef.current[stem.name] = audioBuffer;

                    // Set duration from the first track (assuming all same length)
                    if (loadedCount === 0) {
                        setDuration(audioBuffer.duration);
                    }

                    loadedCount++;
                    setLoadingProgress(Math.round((loadedCount / total) * 100));
                }));
            } catch (err) {
                console.error("Error loading stems:", err);
            } finally {
                setIsLoading(false);
            }
        };

        loadStems();
    }, [stems]);

    const stopAllSources = () => {
        Object.values(sourceNodesRef.current).forEach(node => {
            try { node.stop(); } catch (e) { }
            node.disconnect();
        });
        sourceNodesRef.current = {};

        // Disconnect gains (optional, but cleaner)
        Object.values(gainNodesRef.current).forEach(node => {
            node.disconnect();
        });
        gainNodesRef.current = {};
    };

    const play = useCallback(() => {
        if (audioContextRef.current.state === 'suspended') {
            audioContextRef.current.resume();
        }

        const ctx = audioContextRef.current;
        const startOffset = pauseTimeRef.current;

        // Check if we are at the end
        if (duration > 0 && startOffset >= duration - 0.1) {
            pauseTimeRef.current = 0;
        }

        startTimeRef.current = ctx.currentTime - pauseTimeRef.current;

        // Create and start sources
        stems.forEach(stem => {
            const buffer = buffersRef.current[stem.name];
            if (!buffer) return;

            const source = ctx.createBufferSource();
            source.buffer = buffer;

            const gain = ctx.createGain();
            // Apply current volume/mute
            const vol = muted[stem.name] ? 0 : (volumes[stem.name] ?? 1.0);
            gain.gain.value = vol;

            source.connect(gain);
            gain.connect(ctx.destination);

            source.start(0, pauseTimeRef.current);

            // Store references
            sourceNodesRef.current[stem.name] = source;
            gainNodesRef.current[stem.name] = gain;

            // Handle auto-stop at end (only need one listener)
            if (stem.name === stems[0].name) {
                source.onended = () => {
                    // Check if we actually reached the end (vs just paused)
                    // This is tricky with Web Audio, so we rely on the UI loop for "ended" state
                };
            }
        });

        setIsPlaying(true);

        // UI Loop
        const loop = () => {
            const now = ctx.currentTime;
            const current = now - startTimeRef.current;

            if (current >= duration) {
                setIsPlaying(false);
                pauseTimeRef.current = 0;
                setCurrentTime(0);
                stopAllSources();
                return;
            }

            setCurrentTime(current);
            rafRef.current = requestAnimationFrame(loop);
        };
        loop();

    }, [stems, duration, volumes, muted]);

    const pause = useCallback(() => {
        const ctx = audioContextRef.current;
        pauseTimeRef.current = ctx.currentTime - startTimeRef.current;
        stopAllSources();
        setIsPlaying(false);
        cancelAnimationFrame(rafRef.current);
    }, []);

    const togglePlay = useCallback(() => {
        if (isPlaying) {
            pause();
        } else {
            play();
        }
    }, [isPlaying, play, pause]);

    const seek = useCallback((time) => {
        const wasPlaying = isPlaying;
        if (wasPlaying) {
            stopAllSources();
            cancelAnimationFrame(rafRef.current);
        }

        pauseTimeRef.current = time;
        setCurrentTime(time);

        if (wasPlaying) {
            play();
        }
    }, [isPlaying, play]);

    const setVolume = useCallback((name, val) => {
        setVolumes(prev => ({ ...prev, [name]: val }));

        // Update live gain node
        const gainNode = gainNodesRef.current[name];
        if (gainNode && !muted[name]) {
            gainNode.gain.setValueAtTime(val, audioContextRef.current.currentTime);
        }
    }, [muted]);

    const toggleMute = useCallback((name) => {
        const isNowMuted = !muted[name];
        setMuted(prev => ({ ...prev, [name]: isNowMuted }));

        // Update live gain node
        const gainNode = gainNodesRef.current[name];
        if (gainNode) {
            const vol = isNowMuted ? 0 : (volumes[name] ?? 1.0);
            gainNode.gain.setValueAtTime(vol, audioContextRef.current.currentTime);
        }
    }, [volumes, muted]);

    return {
        isPlaying,
        currentTime,
        duration,
        volumes,
        muted,
        isLoading,
        loadingProgress,
        togglePlay,
        seek,
        setVolume,
        toggleMute
    };
}
