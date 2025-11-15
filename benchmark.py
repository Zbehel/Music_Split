import time
import torch
import torchaudio
from src.separator import MusicSeparator
import psutil
import GPUtil

def benchmark_separation(audio_path: str, model_name: str = 'htdemucs_6s'):
    """Benchmark separation performance"""
    
    # GPU info
    if torch.cuda.is_available():
        gpu = GPUtil.getGPUs()[0]
        print(f"GPU: {gpu.name}, Memory: {gpu.memoryTotal}MB")
    
    # Load model
    print(f"\nLoading model {model_name}...")
    start = time.time()
    separator = MusicSeparator(model_name=model_name)
    load_time = time.time() - start
    print(f"✓ Model loaded in {load_time:.2f}s")
    
    # Load audio
    print(f"\nLoading audio: {audio_path}")
    wav, sr = torchaudio.load(audio_path)
    duration = wav.shape[1] / sr
    print(f"Duration: {duration:.1f}s, Sample rate: {sr}Hz")
    
    # Measure memory before
    mem_before = psutil.Process().memory_info().rss / 1024**2  # MB
    
    # Separate
    print("\nSeparating...")
    start = time.time()
    results = separator.separate(audio_path, "benchmark_output")
    separation_time = time.time() - start
    
    # Measure memory after
    mem_after = psutil.Process().memory_info().rss / 1024**2
    mem_used = mem_after - mem_before
    
    # Results
    print(f"\n{'='*50}")
    print(f"RESULTS:")
    print(f"{'='*50}")
    print(f"Audio duration:       {duration:.1f}s")
    print(f"Separation time:      {separation_time:.2f}s")
    print(f"Real-time factor:     {duration/separation_time:.2f}x")
    print(f"Memory used:          {mem_used:.0f} MB")
    print(f"Throughput:           {duration/separation_time*60:.1f} min/min")
    
    if torch.cuda.is_available():
        print(f"GPU memory used:      {torch.cuda.max_memory_allocated()/1024**2:.0f} MB")
    
    return {
        'duration': duration,
        'separation_time': separation_time,
        'rtf': duration/separation_time,
        'memory_mb': mem_used
    }

if __name__ == "__main__":
    # Test avec différentes durées
    for duration in [30, 60, 180, 300]:  # 30s, 1min, 3min, 5min
        print(f"\n{'#'*50}")
        print(f"Testing {duration}s audio")
        print(f"{'#'*50}")
        
        # Générer audio test
        audio = torch.randn(2, 44100 * duration)
        test_file = f"test_{duration}s.wav"
        torchaudio.save(test_file, audio, 44100)
        
        # Benchmark
        benchmark_separation('test.mp3', 'htdemucs_6s')