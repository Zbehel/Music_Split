
import { useState, useEffect } from 'react';
import { useAudioSync } from './useAudioSync';
import { Play, Pause, Volume2, VolumeX, Upload, Youtube, Download, Music } from 'lucide-react';
import axios from 'axios';
import clsx from 'clsx';

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function App() {
  const [mode, setMode] = useState('upload'); // 'upload' or 'youtube'
  const [file, setFile] = useState(null);
  const [ytUrl, setYtUrl] = useState('');
  const [status, setStatus] = useState('idle'); // idle, uploading, processing, done, error
  const [jobId, setJobId] = useState(null);
  const [stems, setStems] = useState([]); // [{name: 'vocals', url: '...'}]
  const [sessionId, setSessionId] = useState(null);
  const [progress, setProgress] = useState(0);

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

  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState('htdemucs_6s');
  const [errorMsg, setErrorMsg] = useState('');

  // Fetch models on mount
  useEffect(() => {
    axios.get(`${API_URL}/models`)
      .then(res => {
        setModels(res.data.models);
        if (res.data.models.length > 0) {
          setSelectedModel(res.data.models[0]);
        }
      })
      .catch(err => {
        console.error("Failed to fetch models", err);
        setErrorMsg("Failed to connect to API. Check if backend is running.");
      });
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setStatus('uploading');
    setErrorMsg('');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('model_name', selectedModel);

    try {
      const res = await axios.post(`${API_URL}/separate`, formData);
      startPolling(res.data.job_id);
    } catch (e) {
      console.error(e);
      setStatus('error');
      setErrorMsg(e.response?.data?.detail || "Upload failed");
    }
  };

  const handleYoutube = async () => {
    if (!ytUrl) return;
    setStatus('processing');
    setErrorMsg('');

    try {
      const res = await axios.post(`${API_URL}/separate/youtube`, {
        url: ytUrl,
        model_name: selectedModel
      });
      startPolling(res.data.job_id);
    } catch (e) {
      console.error(e);
      setStatus('error');
      setErrorMsg(e.response?.data?.detail || "YouTube processing failed");
    }
  };

  const startPolling = (id) => {
    setJobId(id);
    setStatus('processing');
    setProgress(0);

    // Simulated progress interval
    const progressInterval = setInterval(() => {
      setProgress(prev => {
        if (prev >= 90) return prev;
        // Slow down as we get closer to 90%
        const increment = prev < 50 ? 5 : prev < 80 ? 2 : 0.5;
        return prev + increment;
      });
    }, 1000);

    const interval = setInterval(async () => {
      try {
        const res = await axios.get(`${API_URL}/status/${id}`);
        if (res.data.status === 'done') {
          clearInterval(interval);
          clearInterval(progressInterval);
          setProgress(100);
          setStatus('done');
          setSessionId(res.data.session_id);

          // Parse result to get stems
          const resultStems = res.data.result; // {'vocals': 'path', ...}
          const stemList = Object.keys(resultStems).map(name => ({
            name,
            url: `${API_URL}/download/${res.data.session_id}/${name}`
          }));
          setStems(stemList);
        } else if (res.data.status === 'error') {
          clearInterval(interval);
          clearInterval(progressInterval);
          setStatus('error');
        }
      } catch (e) {
        clearInterval(interval);
        clearInterval(progressInterval);
        setStatus('error');
      }
    }, 2000);
  };

  const handleMixDownload = async () => {
    if (!sessionId) return;

    // Prepare mix payload
    const mixPayload = {
      session_id: sessionId,
      stems: {}
    };

    // Use current volumes (if muted, volume is 0)
    stems.forEach(stem => {
      mixPayload.stems[stem.name] = muted[stem.name] ? 0.0 : (volumes[stem.name] || 1.0);
    });

    try {
      const response = await axios.post(`${API_URL}/mix`, mixPayload, {
        responseType: 'blob'
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'mix.wav');
      document.body.appendChild(link);
      link.click();
    } catch (e) {
      console.error("Mix failed", e);
      alert("Mix failed");
    }
  };

  const formatTime = (t) => {
    const mins = Math.floor(t / 60);
    const secs = Math.floor(t % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen bg-slate-900 text-white p-8 font-sans">
      <div className="max-w-4xl mx-auto">
        <header className="mb-10">
          <div className="flex items-center gap-4 mb-6">
            <div className="w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-500/30">
              <Music className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-cyan-400">
                Music Separator
              </h1>
              <p className="text-slate-400">AI-Powered Stem Separation</p>
            </div>
          </div>

          {/* Model Selector */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-slate-400 mb-2">Select Model</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500 text-white"
            >
              {models.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>

          {/* Error Message */}
          {errorMsg && (
            <div className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-lg text-red-200 text-sm">
              {errorMsg}
            </div>
          )}
        </header>

        {/* INPUT SECTION */}
        <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl p-6 border border-slate-700 mb-8">
          <div className="flex gap-4 mb-6">
            <button
              onClick={() => setMode('upload')}
              className={clsx(
                "flex items-center gap-2 px-4 py-2 rounded-lg transition-all",
                mode === 'upload' ? "bg-indigo-600 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600"
              )}
            >
              <Upload size={18} /> Upload File
            </button>
            <button
              onClick={() => setMode('youtube')}
              className={clsx(
                "flex items-center gap-2 px-4 py-2 rounded-lg transition-all",
                mode === 'youtube' ? "bg-red-600 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600"
              )}
            >
              <Youtube size={18} /> YouTube URL
            </button>
          </div>

          {mode === 'upload' ? (
            <div className="border-2 border-dashed border-slate-600 rounded-xl p-8 text-center hover:border-indigo-500 transition-colors">
              <input
                type="file"
                onChange={(e) => setFile(e.target.files[0])}
                className="block w-full text-sm text-slate-400
                  file:mr-4 file:py-2 file:px-4
                  file:rounded-full file:border-0
                  file:text-sm file:font-semibold
                  file:bg-indigo-50 file:text-indigo-700
                  hover:file:bg-indigo-100"
              />
              <button
                onClick={handleUpload}
                disabled={!file || status === 'processing' || status === 'uploading'}
                className="mt-4 bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {status === 'uploading' ? 'Uploading...' : 'Start Separation'}
              </button>
            </div>
          ) : (
            <div className="flex gap-2">
              <input
                type="text"
                value={ytUrl}
                onChange={(e) => setYtUrl(e.target.value)}
                placeholder="Paste YouTube URL here..."
                className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500"
              />
              <button
                onClick={handleYoutube}
                disabled={!ytUrl || status === 'processing'}
                className="bg-red-600 hover:bg-red-700 text-white px-6 py-2 rounded-lg font-medium disabled:opacity-50 transition-colors"
              >
                Process
              </button>
            </div>
          )}

          {status === 'processing' && (
            <div className="mt-6 text-center">
              <div className="flex justify-between text-sm text-indigo-300 mb-2">
                <span className="font-medium">Processing Audio...</span>
                <span>{Math.round(progress)}%</span>
              </div>
              <div className="w-full bg-slate-700 rounded-full h-3 overflow-hidden shadow-inner">
                <div
                  className="bg-gradient-to-r from-indigo-500 to-cyan-400 h-full rounded-full transition-all duration-500 ease-out shadow-[0_0_10px_rgba(99,102,241,0.5)]"
                  style={{ width: `${progress}%` }}
                >
                  <div className="w-full h-full opacity-30 bg-[linear-gradient(45deg,rgba(255,255,255,0.2)_25%,transparent_25%,transparent_50%,rgba(255,255,255,0.2)_50%,rgba(255,255,255,0.2)_75%,transparent_75%,transparent)] bg-[length:1rem_1rem] animate-[progress-stripes_1s_linear_infinite]"></div>
                </div>
              </div>
              <p className="text-xs text-slate-500 mt-3 animate-pulse">
                AI is separating your tracks. This usually takes 1-2 minutes.
              </p>
            </div>
          )}
        </div>

        {/* PLAYER SECTION */}
        {status === 'done' && stems.length > 0 && (
          <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl p-6 border border-slate-700 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold flex items-center gap-2">
                <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
                Separation Complete
              </h2>
              <button
                onClick={handleMixDownload}
                className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                <Download size={16} /> Download Mix
              </button>
            </div>

            {/* Master Controls */}
            <div className="bg-slate-900/50 rounded-xl p-4 mb-6 border border-slate-700/50">
              <div className="flex items-center gap-4 mb-4">
                <button
                  onClick={togglePlay}
                  className="w-12 h-12 bg-indigo-500 hover:bg-indigo-600 rounded-full flex items-center justify-center shadow-lg shadow-indigo-500/20 transition-all hover:scale-105"
                >
                  {isPlaying ? <Pause fill="white" /> : <Play fill="white" className="ml-1" />}
                </button>
                <div className="flex-1">
                  <input
                    type="range"
                    min="0"
                    max={duration || 100}
                    value={currentTime}
                    onChange={(e) => seek(Number(e.target.value))}
                    className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                  />
                  <div className="flex justify-between text-xs text-slate-400 mt-1">
                    <span>{formatTime(currentTime)}</span>
                    <span>{formatTime(duration)}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Stems List */}
            <div className="space-y-3">
              {stems.map((stem) => (
                <div key={stem.name} className="bg-slate-700/30 rounded-lg p-3 flex items-center gap-4 hover:bg-slate-700/50 transition-colors border border-transparent hover:border-slate-600">
                  <div className="w-24 font-medium capitalize text-slate-300">{stem.name}</div>

                  {/* Hidden Audio Element */}
                  <audio
                    ref={(el) => registerAudio(stem.name, el)}
                    src={stem.url}
                    preload="auto"
                  />

                  <div className="flex-1 flex items-center gap-4">
                    <button
                      onClick={() => toggleMute(stem.name)}
                      className={clsx(
                        "p-2 rounded-lg transition-colors",
                        muted[stem.name] ? "bg-red-500/20 text-red-400" : "bg-slate-600 text-slate-300 hover:bg-slate-500"
                      )}
                    >
                      {muted[stem.name] ? <VolumeX size={18} /> : <Volume2 size={18} />}
                    </button>

                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.01"
                      value={volumes[stem.name] || 1}
                      onChange={(e) => setVolume(stem.name, parseFloat(e.target.value))}
                      className="flex-1 h-1.5 bg-slate-600 rounded-lg appearance-none cursor-pointer accent-indigo-400"
                    />
                  </div>

                  <a
                    href={stem.url}
                    download
                    className="p-2 text-slate-400 hover:text-white hover:bg-slate-600 rounded-lg transition-colors"
                    title="Download Stem"
                  >
                    <Download size={18} />
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;

