import { useState, useEffect, useRef, useCallback } from 'react';

export function useAudioSync(stems) {
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [volumes, setVolumes] = useState({});
    const [muted, setMuted] = useState({});

    const audioRefs = useRef({});
    const rafRef = useRef(null);
    const uiIntervalRef = useRef(null);

    // Initialize state when stems change
    useEffect(() => {
        stems.forEach(stem => {
            if (volumes[stem.name] === undefined) {
                setVolumes(prev => ({ ...prev, [stem.name]: 1.0 }));
                setMuted(prev => ({ ...prev, [stem.name]: false }));
            }
        });
    }, [stems]);

    // Sync volume and mute state to DOM elements (Declarative backup)
    useEffect(() => {
        Object.entries(audioRefs.current).forEach(([name, element]) => {
            if (element) {
                const vol = volumes[name] !== undefined ? volumes[name] : 1.0;
                const isMuted = muted[name] || false;

                // iOS Fix: Use .muted property explicitly
                element.muted = isMuted;
                element.volume = vol;
            }
        });
    }, [volumes, muted]);

    const togglePlay = useCallback(() => {
        if (isPlaying) {
            Object.values(audioRefs.current).forEach(audio => {
                audio.pause();
                audio.playbackRate = 1.0; // Reset rate
            });
            setIsPlaying(false);
            cancelAnimationFrame(rafRef.current);
            clearInterval(uiIntervalRef.current);
        } else {
            let startFrom = currentTime;
            // If we are at the end (within 0.5s margin), restart from beginning
            if (duration > 0 && currentTime >= duration - 0.5) {
                startFrom = 0;
                setCurrentTime(0);
            }

            Object.values(audioRefs.current).forEach(audio => {
                audio.currentTime = startFrom;
                audio.play().catch(e => console.warn("Play error", e));
            });
            setIsPlaying(true);

            // High-frequency Sync Loop (Soft Sync)
            const loop = () => {
                if (Object.values(audioRefs.current).length > 0) {
                    const master = Object.values(audioRefs.current)[0];

                    // Sync others to master using Soft Sync (Playback Rate)
                    Object.values(audioRefs.current).forEach(audio => {
                        if (audio === master) return;

                        const diff = audio.currentTime - master.currentTime;

                        // Thresholds
                        const SYNC_THRESHOLD = 0.05; // 50ms drift allowed
                        const HARD_SEEK_THRESHOLD = 0.5; // >500ms drift -> hard seek

                        if (Math.abs(diff) > HARD_SEEK_THRESHOLD) {
                            // Too far off, force jump (will stutter, but necessary)
                            audio.currentTime = master.currentTime;
                            audio.playbackRate = 1.0;
                        } else if (Math.abs(diff) > SYNC_THRESHOLD) {
                            // Soft Sync: Speed up or slow down
                            // If audio is ahead (diff > 0), slow down (0.95x)
                            // If audio is behind (diff < 0), speed up (1.05x)
                            const targetRate = diff > 0 ? 0.95 : 1.05;
                            if (audio.playbackRate !== targetRate) {
                                audio.playbackRate = targetRate;
                            }
                        } else {
                            // In sync, reset rate
                            if (audio.playbackRate !== 1.0) {
                                audio.playbackRate = 1.0;
                            }
                        }
                    });
                }
                rafRef.current = requestAnimationFrame(loop);
            };
            loop();

            // Low-frequency UI Update Loop (Updates State)
            uiIntervalRef.current = setInterval(() => {
                if (Object.values(audioRefs.current).length > 0) {
                    const master = Object.values(audioRefs.current)[0];
                    setCurrentTime(master.currentTime);

                    // Auto-pause on end
                    if (master.ended) {
                        setIsPlaying(false);
                        cancelAnimationFrame(rafRef.current);
                        clearInterval(uiIntervalRef.current);
                        // Reset rates
                        Object.values(audioRefs.current).forEach(a => a.playbackRate = 1.0);
                    }
                }
            }, 100); // Update UI every 100ms (10fps)
        }
    }, [isPlaying, currentTime, duration]);

    const seek = useCallback((time) => {
        setCurrentTime(time);
        Object.values(audioRefs.current).forEach(audio => {
            audio.currentTime = time;
            audio.playbackRate = 1.0; // Reset sync
        });
    }, []);

    const setVolume = useCallback((name, val) => {
        // 1. Immediate DOM update
        if (audioRefs.current[name]) {
            audioRefs.current[name].volume = val;
        }
        // 2. Update React state
        setVolumes(prev => ({ ...prev, [name]: val }));
    }, []);

    const toggleMute = useCallback((name) => {
        // 1. Immediate DOM update
        const isNowMuted = !muted[name];
        if (audioRefs.current[name]) {
            // iOS Fix: Use .muted property
            audioRefs.current[name].muted = isNowMuted;
        }
        // 2. Update React state
        setMuted(prev => ({ ...prev, [name]: isNowMuted }));
    }, [muted]);

    const registerAudio = useCallback((name, element) => {
        if (element) {
            audioRefs.current[name] = element;
            // Initial sync
            const vol = volumes[name] !== undefined ? volumes[name] : 1.0;
            const isMuted = muted[name] || false;

            element.volume = vol;
            element.muted = isMuted;

            if (name === stems[0]?.name) {
                element.onloadedmetadata = () => {
                    setDuration(element.duration);
                }
            }
        } else {
            delete audioRefs.current[name];
        }
    }, [stems, volumes, muted]);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            cancelAnimationFrame(rafRef.current);
            clearInterval(uiIntervalRef.current);
        };
    }, []);

    return {
        isPlaying,
        currentTime,
        duration,
        volumes,
        muted,
        togglePlay,
        seek,
        setVolume,
        toggleMute,
        registerAudio
    };
}
