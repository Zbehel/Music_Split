import { useState, useEffect, useRef, useCallback } from 'react';

export function useWebAudio(stems) {
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [volumes, setVolumes] = useState({});
    const [muted, setMuted] = useState({});
    const [isLoading, setIsLoading] = useState(false);
    const [loadingProgress, setLoadingProgress] = useState(0);

    const audioContextRef = useRef(null);
    const gainNodesRef = useRef({});
    const analyzerNodesRef = useRef({});
    const sourceNodesRef = useRef({});
    const audioBuffersRef = useRef({});
    const startTimeRef = useRef(0);
    const pauseTimeRef = useRef(0);
    const rafRef = useRef(null);

    // Initialize AudioContext
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

    // Load and decode audio files
    useEffect(() => {
        if (!stems || stems.length === 0 || !audioContextRef.current) return;

        const loadStems = async () => {
            setIsLoading(true);
            setLoadingProgress(0);

            // Stop any current playback
            stop();

            // Reset state
            audioBuffersRef.current = {};
            gainNodesRef.current = {};
            analyzerNodesRef.current = {};
            setVolumes({});
            setMuted({});
            pauseTimeRef.current = 0;
            setCurrentTime(0);

            let loadedCount = 0;
            const totalStems = stems.length;

            try {
                await Promise.all(stems.map(async (stem) => {
                    try {
                        const response = await fetch(stem.url);
                        const arrayBuffer = await response.arrayBuffer();
                        const audioBuffer = await audioContextRef.current.decodeAudioData(arrayBuffer);

                        audioBuffersRef.current[stem.name] = audioBuffer;

                        // Initialize volume state
                        setVolumes(prev => ({ ...prev, [stem.name]: 1.0 }));
                        setMuted(prev => ({ ...prev, [stem.name]: false }));

                        // Create GainNode for this stem
                        const gainNode = audioContextRef.current.createGain();

                        // Create AnalyserNode for this stem
                        const analyzer = audioContextRef.current.createAnalyser();
                        analyzer.fftSize = 256;
                        analyzerNodesRef.current[stem.name] = analyzer;

                        // Connect: Source -> Analyser -> Gain -> Destination
                        // Note: Source is connected in play()
                        analyzer.connect(gainNode);
                        gainNode.connect(audioContextRef.current.destination);

                        gainNodesRef.current[stem.name] = gainNode;

                        // Set duration from the first stem (assuming all are same length)
                        if (stem.name === stems[0].name) {
                            setDuration(audioBuffer.duration);
                        }

                        loadedCount++;
                        setLoadingProgress((loadedCount / totalStems) * 100);
                    } catch (err) {
                        console.error(`Failed to load stem ${stem.name}:`, err);
                    }
                }));
            } catch (err) {
                console.error("Error loading stems:", err);
            } finally {
                setIsLoading(false);
            }
        };

        loadStems();
    }, [stems]);

    const play = useCallback(() => {
        if (!audioContextRef.current || isLoading) return;

        if (audioContextRef.current.state === 'suspended') {
            audioContextRef.current.resume();
        }

        const ctx = audioContextRef.current;
        const startOffset = pauseTimeRef.current;
        startTimeRef.current = ctx.currentTime - startOffset;

        // Create and start source nodes
        Object.entries(audioBuffersRef.current).forEach(([name, buffer]) => {
            const source = ctx.createBufferSource();
            source.buffer = buffer;

            // Connect to analyzer node (which connects to gain -> destination)
            if (analyzerNodesRef.current[name]) {
                source.connect(analyzerNodesRef.current[name]);
            } else if (gainNodesRef.current[name]) {
                // Fallback direct to gain if no analyzer
                source.connect(gainNodesRef.current[name]);
            }

            source.start(0, startOffset);
            sourceNodesRef.current[name] = source;

            // Handle auto-stop at end
            source.onended = () => {
                if (Math.abs(ctx.currentTime - startTimeRef.current - buffer.duration) < 0.1) {
                    setIsPlaying(false);
                    pauseTimeRef.current = 0;
                    setCurrentTime(0);
                    cancelAnimationFrame(rafRef.current);
                }
            };
        });

        setIsPlaying(true);

        // Animation loop for UI update
        const updateUI = () => {
            const current = ctx.currentTime - startTimeRef.current;
            if (current >= duration) {
                setCurrentTime(duration);
                setIsPlaying(false);
            } else {
                setCurrentTime(current);
                rafRef.current = requestAnimationFrame(updateUI);
            }
        };
        updateUI();

    }, [isLoading, duration]);

    const stop = useCallback(() => {
        if (!audioContextRef.current) return;

        Object.values(sourceNodesRef.current).forEach(source => {
            try {
                source.stop();
                source.disconnect();
            } catch (e) {
                // Ignore errors if already stopped
            }
        });
        sourceNodesRef.current = {};
        setIsPlaying(false);
        cancelAnimationFrame(rafRef.current);

        // Save pause time
        if (isPlaying) {
            pauseTimeRef.current = audioContextRef.current.currentTime - startTimeRef.current;
        }
    }, [isPlaying]);

    const togglePlay = useCallback(() => {
        if (isPlaying) {
            stop();
        } else {
            play();
        }
    }, [isPlaying, play, stop]);

    const seek = useCallback((time) => {
        const wasPlaying = isPlaying;
        stop();
        pauseTimeRef.current = Math.max(0, Math.min(time, duration));
        setCurrentTime(pauseTimeRef.current);

        if (wasPlaying) {
            play();
        }
    }, [isPlaying, duration, stop, play]);

    const setVolume = useCallback((name, val) => {
        if (gainNodesRef.current[name]) {
            gainNodesRef.current[name].gain.value = muted[name] ? 0 : val;
        }
        setVolumes(prev => ({ ...prev, [name]: val }));
    }, [muted]);

    const toggleMute = useCallback((name, solo = false) => {
        if (solo) {
            // Solo logic: mute everyone else, unmute target
            const newMuted = {};
            Object.keys(volumes).forEach(n => {
                newMuted[n] = (n !== name);
            });

            // Apply to nodes
            Object.entries(gainNodesRef.current).forEach(([n, node]) => {
                node.gain.value = newMuted[n] ? 0 : volumes[n];
            });
            setMuted(newMuted);
        } else {
            // Normal toggle
            const isNowMuted = !muted[name];
            if (gainNodesRef.current[name]) {
                gainNodesRef.current[name].gain.value = isNowMuted ? 0 : volumes[name];
            }
            setMuted(prev => ({ ...prev, [name]: isNowMuted }));
        }
    }, [muted, volumes]);

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
        toggleMute,
        analyzerNodes: analyzerNodesRef.current
    };
}
