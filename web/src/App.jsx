import { useState, useEffect, useRef, useCallback } from 'react';
import { useAudioSync } from './useAudioSync';
import { Play, Pause, Volume2, VolumeX, Upload, Youtube, Download, Music, Layers, Activity, Settings, CheckCircle, AlertTriangle } from 'lucide-react';
import axios from 'axios';
import clsx from 'clsx';
import Spectrum from './Spectrum';

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const STEM_COLORS = {
  vocals: '#6366f1', // Indigo
  drums: '#ef4444', // Red
  bass: '#a855f7', // Purple
  other: '#10b981', // Emerald
  original: '#f59e0b' // Amber
};

// Error Boundary Component
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("Uncaught error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#0f172a] text-white flex flex-col items-center justify-center p-8">
          <AlertTriangle size={48} className="text-red-500 mb-4" />
          <h1 className="text-2xl font-bold mb-2">Something went wrong</h1>
          <p className="text-slate-400 mb-6 text-center max-w-md">
            The application encountered an unexpected error.
          </p>
          <div className="bg-slate-800 p-4 rounded-lg font-mono text-xs text-red-300 mb-6 max-w-2xl overflow-auto">
            {this.state.error && this.state.error.toString()}
          </div>
          <button
            onClick={() => window.location.reload()}
            className="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2 rounded-lg font-medium transition-colors"
          >
            Reload Application
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

import React from 'react';

function AppContent() {
  // --- STATE ---
  const [mode, setMode] = useState('upload'); // 'upload' | 'youtube'
  const [file, setFile] = useState(null);
  const [ytUrl, setYtUrl] = useState('');

  // Strict State Machine: 'idle' | 'uploading' | 'processing' | 'done' | 'error'
  const [status, setStatus] = useState('idle');
  const [progress, setProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');

  // Data
  const [jobId, setJobId] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [stems, setStems] = useState([]);
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState('htdemucs_6s');

  // Audio Refs
  const [audioElements, setAudioElements] = useState({});

  // --- HOOKS ---
  const {
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
  } = useAudioSync(stems);

  // --- EFFECTS ---

  // 1. Fetch Models on Mount
  useEffect(() => {
    axios.get(`${API_URL}/models`)
      .then(res => {
        setModels(res.data.models || []);
        if (res.data.models?.length > 0) {
          setSelectedModel(res.data.models[0]);
        }
      })
      .catch(err => {
        console.error("Failed to fetch models", err);
        setErrorMsg("Could not connect to backend API.");
      });
  }, []);

  // 2. Polling Logic (Only active when status === 'processing')
  useEffect(() => {
    if (status !== 'processing' || !jobId) return;

    console.log(`[Polling] Started for Job ID: ${jobId}`);

    // Fake progress incrementer for visual feedback
    const progressInterval = setInterval(() => {
      setProgress(prev => {
        if (prev >= 90) return prev;
        return prev + (prev < 50 ? 5 : 1);
      });
    }, 1000);

    // Status Poller
    const pollInterval = setInterval(async () => {
      try {
        const res = await axios.get(`${API_URL}/status/${jobId}`);
        const data = res.data;

        if (data.status === 'done') {
          console.log("[Polling] Job Done!", data);
          clearInterval(pollInterval);
          clearInterval(progressInterval);

          handleJobSuccess(data);
        } else if (data.status === 'error') {
          console.error("[Polling] Job Error:", data.error);
          clearInterval(pollInterval);
          clearInterval(progressInterval);

          setStatus('error');
          setErrorMsg(data.error || "Processing failed on server.");
        } else {
          // Still processing...
          if (data.session_id && !sessionId) {
            setSessionId(data.session_id);
          }
        }
      } catch (e) {
        console.warn("[Polling] Network error (retrying...)", e);
      }
    }, 3000);

    return () => {
      clearInterval(pollInterval);
      clearInterval(progressInterval);
    };
  }, [status, jobId]);

  // --- HANDLERS ---

  const handleJobSuccess = (data) => {
    setProgress(100);
    setSessionId(data.session_id);

    // Construct stem objects
    const resultStems = data.result || {};
    const newStems = Object.keys(resultStems).map(name => ({
      name,
      url: `${API_URL}/download/${data.session_id}/${name}`,
      color: STEM_COLORS[name] || '#888'
    }));

    setStems(newStems);
    setStatus('done');
  };

  const resetState = () => {
    setStatus('idle');
    setErrorMsg('');
    setStems([]);
    setJobId(null);
    setProgress(0);
    setSessionId(null);
    setAudioElements({});
  };

  const handleUpload = async () => {
    if (!file) return;
    resetState();
    setStatus('uploading');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('model_name', selectedModel);

    try {
      const res = await axios.post(`${API_URL}/separate`, formData);
      setJobId(res.data.job_id);
      setStatus('processing');
    } catch (e) {
      console.error("Upload failed", e);
      setStatus('error');
      setErrorMsg(e.response?.data?.detail || "Upload failed. Check connection.");
    }
  };

  const handleYoutube = async () => {
    if (!ytUrl) return;
    resetState();
    setStatus('processing'); // Skip uploading state for YT

    try {
      const res = await axios.post(`${API_URL}/separate/youtube`, {
        url: ytUrl,
        model_name: selectedModel
      });
      setJobId(res.data.job_id);
    } catch (e) {
      console.error("YouTube failed", e);
      setStatus('error');
      setErrorMsg(e.response?.data?.detail || "YouTube processing failed.");
    }
  };

  const handleMixDownload = async () => {
    if (!sessionId) return;

    const mixPayload = {
      session_id: sessionId,
      stems: {}
    };

    stems.forEach(stem => {
      mixPayload.stems[stem.name] = muted[stem.name] ? 0.0 : (volumes[stem.name] || 1.0);
    });

    try {
      const response = await axios.post(`${API_URL}/mix`, mixPayload, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'mix.flac');
      document.body.appendChild(link);
      link.click();
    } catch (e) {
      console.error("Mix download failed", e);
      alert("Failed to download mix.");
    }
  };

  const formatTime = (t) => {
    if (!t && t !== 0) return "0:00";
    const mins = Math.floor(t / 60);
    const secs = Math.floor(t % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // --- RENDER ---
  return (
    <div className="flex flex-col md:flex-row min-h-screen md:h-screen w-screen bg-[#0f172a] text-white md:overflow-hidden font-sans">

      {/* SIDEBAR */}
      <div className="w-full md:w-80 h-auto md:h-full flex-shrink-0 bg-slate-900/50 border-b md:border-b-0 md:border-r border-white/5 p-6 flex flex-col gap-6 overflow-y-auto backdrop-blur-md z-20">

        {/* Header */}
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-cyan-500 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Music className="text-white" size={20} />
          </div>
          <div>
            <h1 className="font-bold text-xl tracking-tight">Music Split</h1>
            <p className="text-xs text-slate-400">AI Stem Separator</p>
          </div>
        </div>

        {/* Mode Switch */}
        <div className="bg-slate-800/50 p-1 rounded-xl flex text-sm font-medium">
          <button
            onClick={() => setMode('upload')}
            className={clsx("flex-1 py-2 rounded-lg transition-all flex items-center justify-center gap-2", mode === 'upload' ? "bg-indigo-600 text-white shadow-md" : "text-slate-400 hover:text-white")}
          >
            <Upload size={16} /> Upload
          </button>
          <button
            onClick={() => setMode('youtube')}
            className={clsx("flex-1 py-2 rounded-lg transition-all flex items-center justify-center gap-2", mode === 'youtube' ? "bg-red-600 text-white shadow-md" : "text-slate-400 hover:text-white")}
          >
            <Youtube size={16} /> YouTube
          </button>
        </div>

        {/* Input Area */}
        <div className="flex-1 flex flex-col gap-4">
          {mode === 'upload' ? (
            <div className="border-2 border-dashed border-slate-700 rounded-2xl p-6 text-center hover:border-indigo-500/50 transition-colors bg-slate-800/20">
              <input
                type="file"
                onChange={(e) => setFile(e.target.files[0])}
                className="hidden"
                id="file-upload"
              />
              <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center gap-3">
                <div className="w-12 h-12 bg-indigo-500/10 rounded-full flex items-center justify-center text-indigo-400">
                  <Upload size={24} />
                </div>
                <span className="text-sm text-slate-300 font-medium">
                  {file ? file.name : "Click to browse"}
                </span>
                <span className="text-xs text-slate-500">Supports MP3, WAV, FLAC</span>
              </label>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium text-slate-400 ml-1">YouTube URL</label>
              <input
                type="text"
                value={ytUrl}
                onChange={(e) => setYtUrl(e.target.value)}
                placeholder="https://youtube.com/watch?v=..."
                className="bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-indigo-500 transition-all"
              />
            </div>
          )}

          {/* Model Selector */}
          <div className="flex flex-col gap-2">
            <label className="text-xs font-medium text-slate-400 ml-1">Separation Model</label>
            <div className="relative">
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full appearance-none bg-slate-800 border border-slate-700 text-slate-300 py-3 pl-4 pr-10 rounded-xl text-sm focus:outline-none focus:border-indigo-500 cursor-pointer"
              >
                {models.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
              <Settings className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" size={14} />
            </div>
          </div>

          {/* Action Button */}
          <button
            onClick={mode === 'upload' ? handleUpload : handleYoutube}
            disabled={status === 'processing' || status === 'uploading' || (mode === 'upload' && !file) || (mode === 'youtube' && !ytUrl)}
            className="mt-auto w-full bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white py-3.5 rounded-xl font-bold shadow-lg shadow-indigo-500/25 disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-[0.98]"
          >
            {status === 'processing' ? 'Processing...' : status === 'uploading' ? 'Uploading...' : 'Start Separation'}
          </button>

          {/* Status & Progress */}
          {(status === 'processing' || status === 'uploading') && (
            <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
              <div className="flex justify-between text-xs text-indigo-300 mb-2 font-medium">
                <span className="flex items-center gap-2"><Activity className="animate-spin" size={12} /> {status === 'uploading' ? 'Uploading...' : 'Processing...'}</span>
                <span>{Math.round(progress)}%</span>
              </div>
              <div className="w-full bg-slate-700 rounded-full h-1.5 overflow-hidden">
                <div className="bg-indigo-500 h-full rounded-full transition-all duration-300" style={{ width: `${progress}%` }}></div>
              </div>
            </div>
          )}

          {/* Error Message */}
          {errorMsg && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs text-center">
              {errorMsg}
            </div>
          )}
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div className="flex-1 flex flex-col relative md:overflow-hidden">

        {/* Background Gradients */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-[-20%] right-[-10%] w-[60%] h-[60%] bg-indigo-600/10 rounded-full blur-[150px]" />
          <div className="absolute bottom-[-20%] left-[-10%] w-[50%] h-[50%] bg-cyan-600/10 rounded-full blur-[150px]" />
        </div>

        {/* Top Section: Master Control */}
        <div className="h-auto p-8 flex flex-col justify-center relative z-10 border-b border-white/5 bg-slate-900/20 backdrop-blur-sm">
          {status === 'done' && stems.length > 0 ? (
            <div className="max-w-4xl mx-auto w-full">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className="text-3xl font-bold text-white mb-1">Stems Master Control</h2>
                  <p className="text-slate-400 flex items-center gap-2 text-sm">
                    <Layers size={14} /> Control all separated stems
                  </p>
                </div>
                <div className="flex items-center gap-2 px-4 py-2 bg-green-500/10 text-green-400 rounded-full border border-green-500/20 text-sm font-medium">
                  <CheckCircle size={16} /> Separation Complete
                </div>
              </div>

              {/* Master Controls */}
              <div className="bg-slate-800/40 border border-white/10 rounded-2xl p-6 backdrop-blur-md shadow-xl">
                <div className="flex items-center gap-6">
                  <div className="flex items-center gap-4">
                    <button
                      onClick={togglePlay}
                      className="w-14 h-14 bg-indigo-500 hover:bg-indigo-400 rounded-full flex items-center justify-center shadow-lg shadow-indigo-500/30 transition-all hover:scale-105 active:scale-95"
                    >
                      {isPlaying ? <Pause fill="white" size={24} /> : <Play fill="white" size={24} ml={1} />}
                    </button>
                    <div>
                      <div className="text-xs font-bold text-indigo-300 uppercase tracking-wider mb-1">Master Playback</div>
                      <div className="text-sm text-slate-300 font-mono">{formatTime(currentTime)} / {formatTime(duration)}</div>
                    </div>
                  </div>

                  {/* Master Seek Bar */}
                  <div className="flex-1 relative h-3 group cursor-pointer">
                    <div className="absolute inset-0 bg-slate-700 rounded-full"></div>
                    <div
                      className="absolute top-0 left-0 h-full bg-gradient-to-r from-indigo-500 to-cyan-500 rounded-full"
                      style={{ width: `${(currentTime / duration) * 100}%` }}
                    ></div>
                    <input
                      type="range"
                      min="0"
                      max={duration || 100}
                      value={currentTime}
                      onChange={(e) => seek(Number(e.target.value))}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    />
                  </div>

                  <button
                    onClick={handleMixDownload}
                    className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-all"
                    title="Download mix with current volume settings"
                  >
                    <Download size={16} /> Download Mix
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center text-slate-500">
              <div className="w-20 h-20 bg-slate-800/50 rounded-full flex items-center justify-center mx-auto mb-4">
                <Music size={32} className="opacity-50" />
              </div>
              <h3 className="text-xl font-medium text-slate-400">Ready to Separate</h3>
              <p className="text-sm opacity-60">Upload a file or paste a YouTube link to begin</p>
            </div>
          )}
        </div>

        {/* Bottom Section: Stems Grid */}
        <div className="flex-1 p-8 md:overflow-y-auto bg-slate-900/30">
          {status === 'done' && stems.length > 0 ? (
            <div className="w-full grid gap-3 pb-20">
              {stems.map((stem) => (
                <div
                  key={stem.name}
                  className="group flex items-center gap-6 bg-slate-800/40 hover:bg-slate-800/60 border border-white/5 hover:border-indigo-500/30 rounded-xl p-4 transition-all duration-300"
                >
                  {/* Hidden Audio */}
                  <audio
                    ref={(el) => {
                      registerAudio(stem.name, el);
                      if (el && audioElements[stem.name] !== el) {
                        setAudioElements(prev => ({ ...prev, [stem.name]: el }));
                      }
                    }}
                    src={stem.url}
                    preload="auto"
                    crossOrigin="anonymous"
                  />

                  {/* Stem Info */}
                  <div className="w-24 shrink-0">
                    <div className="text-sm font-bold uppercase tracking-wider text-slate-300">{stem.name}</div>
                    <div className="h-1 w-8 mt-1 rounded-full" style={{ backgroundColor: STEM_COLORS[stem.name] }}></div>
                  </div>

                  {/* Controls */}
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => toggleMute(stem.name)}
                      className={clsx(
                        "p-2 rounded-lg transition-all",
                        muted[stem.name] ? "bg-red-500/10 text-red-400" : "bg-slate-700/50 text-slate-400 hover:text-white"
                      )}
                    >
                      {muted[stem.name] ? <VolumeX size={18} /> : <Volume2 size={18} />}
                    </button>
                  </div>

                  {/* Volume Slider */}
                  <div className="w-32 relative h-1.5 bg-slate-700/50 rounded-full overflow-hidden group-hover:h-2 transition-all">
                    <div
                      className={clsx("absolute top-0 left-0 h-full rounded-full transition-all", muted[stem.name] ? "bg-slate-600" : "bg-indigo-500")}
                      style={{ width: `${(volumes[stem.name] || 0) * 100}%`, backgroundColor: muted[stem.name] ? undefined : STEM_COLORS[stem.name] }}
                    ></div>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.01"
                      value={volumes[stem.name] || 1}
                      onChange={(e) => setVolume(stem.name, parseFloat(e.target.value))}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    />
                  </div>

                  {/* Spectrum Visualizer */}
                  <div className="flex-1 h-[40px] flex items-center justify-center bg-slate-900/50 rounded-lg border border-white/5">
                    <Spectrum
                      audioNode={audioElements[stem.name]}
                      color={STEM_COLORS[stem.name] || '#cbd5e1'}
                    />
                  </div>

                  {/* Download */}
                  <a
                    href={stem.url}
                    download
                    className="p-2 text-slate-500 hover:text-indigo-400 hover:bg-indigo-500/10 rounded-lg transition-all"
                    title="Download Stem"
                  >
                    <Download size={18} />
                  </a>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-slate-600 opacity-50">
              <Layers size={48} className="mb-4" />
              <p>Stems will appear here after separation</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AppContent />
    </ErrorBoundary>
  );
}
