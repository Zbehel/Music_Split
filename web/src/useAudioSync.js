import { useState, useEffect, useRef, useCallback } from 'react';

export function useAudioSync(stems) {
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [volumes, setVolumes] = useState({});
    const [muted, setMuted] = useState({});

    const audioRefs = useRef({});
    const rafRef = useRef(null);

    // Initialize refs when stems change
    useEffect(() => {
        stems.forEach(stem => {
            if (!volumes[stem.name]) {
                setVolumes(prev => ({ ...prev, [stem.name]: 1.0 }));
                setMuted(prev => ({ ...prev, [stem.name]: false }));
            }
        });
    }, [stems]);

    const togglePlay = useCallback(() => {
        if (isPlaying) {
            Object.values(audioRefs.current).forEach(audio => audio.pause());
            setIsPlaying(false);
            cancelAnimationFrame(rafRef.current);
        } else {
            Object.values(audioRefs.current).forEach(audio => {
                audio.currentTime = currentTime;
                audio.play().catch(e => console.warn("Play error", e));
            });
            setIsPlaying(true);

            // Sync loop
            const loop = () => {
                if (Object.values(audioRefs.current).length > 0) {
                    const master = Object.values(audioRefs.current)[0];
                    setCurrentTime(master.currentTime);

                    // Sync others
                    Object.values(audioRefs.current).forEach(audio => {
                        if (Math.abs(audio.currentTime - master.currentTime) > 0.1) {
                            audio.currentTime = master.currentTime;
                        }
                    });
                }
                rafRef.current = requestAnimationFrame(loop);
            };
            loop();
        }
    }, [isPlaying, currentTime]);

    const seek = useCallback((time) => {
        setCurrentTime(time);
        Object.values(audioRefs.current).forEach(audio => {
            audio.currentTime = time;
        });
    }, []);

    const setVolume = useCallback((name, val) => {
        setVolumes(prev => ({ ...prev, [name]: val }));
        if (audioRefs.current[name] && !muted[name]) {
            audioRefs.current[name].volume = val;
        }
    }, [muted]);

    const toggleMute = useCallback((name) => {
        setMuted(prev => {
            const newMuted = !prev[name];
            if (audioRefs.current[name]) {
                audioRefs.current[name].volume = newMuted ? 0 : volumes[name];
            }
            return { ...prev, [name]: newMuted };
        });
    }, [volumes]);

    const registerAudio = useCallback((name, element) => {
        if (element) {
            audioRefs.current[name] = element;
            element.volume = muted[name] ? 0 : (volumes[name] || 1.0);

            if (name === stems[0]?.name) {
                element.onloadedmetadata = () => {
                    setDuration(element.duration);
                }
            }
        } else {
            delete audioRefs.current[name];
        }
    }, [stems, volumes, muted]);

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
