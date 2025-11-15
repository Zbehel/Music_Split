import time
import torch
import torchaudio
from src.separator import MusicSeparator, list_available_models
from pathlib import Path
import psutil
try:
    import GPUtil
    HAS_GPUTIL = True
except ImportError:
    HAS_GPUTIL = False
    print("Warning: GPUtil not installed. GPU metrics will be limited.")


def generate_test_audio(duration_seconds: int, output_path: str) -> str:
    """Generate test audio file"""
    sample_rate = 44100
    samples = sample_rate * duration_seconds
    audio = torch.randn(2, samples)  # Stereo
    torchaudio.save(output_path, audio, sample_rate)
    return output_path


def benchmark_separation(
    audio_path: str, 
    model_name: str = 'htdemucs',
    output_dir: str = 'benchmark_output'
):
    """Benchmark separation performance"""
    
    print(f"\n{'='*60}")
    print(f"BENCHMARKING MODEL: {model_name}")
    print(f"{'='*60}\n")
    
    # GPU info
    if torch.cuda.is_available():
        if HAS_GPUTIL:
            gpu = GPUtil.getGPUs()[0]
            print(f"GPU: {gpu.name}")
            print(f"GPU Memory Total: {gpu.memoryTotal}MB")
            print(f"GPU Memory Free: {gpu.memoryFree}MB\n")
        else:
            print(f"GPU: CUDA available")
            print(f"GPU Name: {torch.cuda.get_device_name(0)}\n")
    else:
        print("Device: CPU\n")
    
    # Load model
    print(f"Loading model '{model_name}'...")
    start = time.time()
    separator = MusicSeparator(model_name=model_name)
    load_time = time.time() - start
    print(f"✓ Model loaded in {load_time:.2f}s")
    print(f"✓ Device: {separator.device}")
    print(f"✓ Stems: {', '.join(separator.stems)}\n")
    
    # Load audio
    print(f"Loading audio: {audio_path}")
    wav, sr = torchaudio.load(audio_path)
    duration = wav.shape[1] / sr
    print(f"✓ Duration: {duration:.1f}s")
    print(f"✓ Sample rate: {sr}Hz")
    print(f"✓ Channels: {wav.shape[0]}\n")
    
    # Measure memory before
    mem_before = psutil.Process().memory_info().rss / 1024**2  # MB
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    
    # Separate
    print("Starting separation...")
    start = time.time()
    results = separator.separate(audio_path, output_dir)
    separation_time = time.time() - start
    
    # Measure memory after
    mem_after = psutil.Process().memory_info().rss / 1024**2
    mem_used = mem_after - mem_before
    
    # Results
    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"{'='*60}")
    print(f"Audio duration:       {duration:.1f}s ({duration/60:.2f} min)")
    print(f"Separation time:      {separation_time:.2f}s")
    print(f"Real-time factor:     {duration/separation_time:.2f}x")
    print(f"Throughput:           {duration/separation_time*60:.1f} min/min")
    print(f"RAM used:             {mem_used:.0f} MB")
    
    if torch.cuda.is_available():
        gpu_mem = torch.cuda.max_memory_allocated()/1024**2
        print(f"GPU memory used:      {gpu_mem:.0f} MB")
    
    print(f"\nGenerated {len(results)} stems:")
    for stem, path in results.items():
        size = Path(path).stat().st_size / 1024**2  # MB
        print(f"  - {stem}: {size:.1f} MB")
    
    return {
        'model': model_name,
        'duration': duration,
        'separation_time': separation_time,
        'rtf': duration/separation_time,
        'memory_mb': mem_used,
        'num_stems': len(results)
    }


def run_duration_benchmarks(
    model_name: str = 'htdemucs',
    durations: list = [10, 30, 60, 180]
):
    """Run benchmarks for different audio durations"""
    results = []
    
    print(f"\n{'#'*60}")
    print(f"DURATION BENCHMARKS - Model: {model_name}")
    print(f"{'#'*60}\n")
    
    for duration in durations:
        print(f"\n{'='*60}")
        print(f"Testing {duration}s audio")
        print(f"{'='*60}")
        
        # Generate audio test
        test_file = f"test_{duration}s.wav"
        generate_test_audio(duration, test_file)
        
        # Benchmark
        result = benchmark_separation(test_file, model_name, f"benchmark_output_{duration}s")
        results.append(result)
        
        # Cleanup test file
        Path(test_file).unlink()
    
    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY - {model_name}")
    print(f"{'='*60}")
    print(f"{'Duration':<12} {'Time':<10} {'RTF':<10} {'RAM (MB)':<12}")
    print(f"{'-'*60}")
    for r in results:
        print(f"{r['duration']:>8.0f}s   {r['separation_time']:>6.1f}s   {r['rtf']:>6.2f}x   {r['memory_mb']:>8.0f} MB")
    
    return results


def compare_models(
    models: list = None,
    audio_duration: int = 30
):
    """Compare different models on the same audio"""
    if models is None:
        models = ['htdemucs', 'htdemucs_6s']
    
    print(f"\n{'#'*60}")
    print(f"MODEL COMPARISON - {audio_duration}s audio")
    print(f"{'#'*60}\n")
    
    # Generate test audio
    test_file = f"test_compare_{audio_duration}s.wav"
    generate_test_audio(audio_duration, test_file)
    
    results = []
    for model in models:
        try:
            result = benchmark_separation(
                test_file, 
                model, 
                f"benchmark_output_{model}"
            )
            results.append(result)
        except Exception as e:
            print(f"Error with model {model}: {e}")
    
    # Cleanup
    Path(test_file).unlink()
    
    # Summary
    print(f"\n{'='*60}")
    print(f"MODEL COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"{'Model':<20} {'Stems':<8} {'Time':<10} {'RTF':<10} {'RAM (MB)':<12}")
    print(f"{'-'*60}")
    for r in results:
        print(f"{r['model']:<20} {r['num_stems']:<8} {r['separation_time']:>6.1f}s   {r['rtf']:>6.2f}x   {r['memory_mb']:>8.0f} MB")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Benchmark music separation')
    parser.add_argument('--mode', choices=['single', 'duration', 'compare'], 
                       default='duration', help='Benchmark mode')
    parser.add_argument('--model', type=str, default='htdemucs',
                       help='Model to benchmark')
    parser.add_argument('--audio', type=str, help='Path to audio file')
    parser.add_argument('--duration', type=int, default=30,
                       help='Test audio duration in seconds')
    
    args = parser.parse_args()
    
    if args.mode == 'single':
        if args.audio:
            benchmark_separation(args.audio, args.model)
        else:
            test_file = f"test_{args.duration}s.wav"
            generate_test_audio(args.duration, test_file)
            benchmark_separation(test_file, args.model)
            Path(test_file).unlink()
    
    elif args.mode == 'duration':
        run_duration_benchmarks(args.model)
    
    elif args.mode == 'compare':
        available = list_available_models()
        print(f"Available models: {available}")
        compare_models(models=['htdemucs', 'htdemucs_6s'])
