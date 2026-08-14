# Local Whisper benchmark

Benchmark date: 2026-08-04

## Outcome

The selected production path is **Whisper large-v3-turbo Q5_0 through a persistent `whisper.cpp` Vulkan server on the Radeon 8060S**. It keeps all audio on this machine and returned an 11-second reference clip in a **0.241-second median** once resident (about **45.6x real time**).

The original requested recording could not be benchmarked. The old configuration targeted the nonexistent PipeWire source `alsa_input.pci-0000_00_1f.3.analog-stereo`; the old API workflow then removed `recording.wav`. The source is now the current Studio Display microphone, and the workflow retains the newest complete audio as `last-recording.wav`.

## Test system and method

- CPU: AMD Ryzen AI Max+ 395, 16 cores / 32 threads, AVX-512
- GPU: Radeon 8060S, Mesa RADV Vulkan 1.4
- Memory: 64 GiB unified memory
- Runtime: `whisper.cpp` v1.9.1, release build, Vulkan and native CPU variants
- Model: OpenAI Whisper large-v3-turbo, full/Q8_0/Q5_0 official GGML conversions
- Audio: upstream `jfk.wav`, mono PCM S16LE, 16 kHz, exactly 11.0 seconds
- Decode: English, temperature 0, greedy (`beam-size=1`, `best-of=1`), no fallback, no timestamps
- Each Vulkan CLI result below is the median of five page-cache-warm process launches. Every launch still loads its model; the server measurements keep Q5 resident.

All three model forms produced the same text:

> And so, my fellow Americans, ask not what your country can do for you, ask what you can do for your country.

## Single-request latency

| Path | Median wall time | P95 | Real-time factor | Audio speed |
|---|---:|---:|---:|---:|
| Resident Vulkan server, Q5 | **0.241 s** | **0.243 s** | **0.022** | **45.6x** |
| Vulkan CLI, Q5 | 0.799 s | 0.828 s | 0.073 | 13.8x |
| Vulkan CLI, Q8 | 0.828 s | 0.835 s | 0.075 | 13.3x |
| Vulkan CLI, full model | 0.967 s | 0.973 s | 0.088 | 11.4x |
| CPU CLI, Q5, 16 threads | 2.616 s | one run | 0.238 | 4.2x |

Q5 was 3.6% faster than Q8 and 21% faster than the full model in the CLI test, with identical output on this clip. More importantly, keeping Q5 resident removed roughly 0.56 seconds of per-invocation overhead.

The first request after a fresh user-service start took 0.453 seconds. Subsequent requests settled at about 0.24 seconds.

## CPU scaling

| Q5 CPU threads | Wall time | User CPU time | Approx. average cores used |
|---:|---:|---:|---:|
| 4 | 8.711 s | 34.438 s | 4.0 |
| 8 | 4.634 s | 36.340 s | 7.8 |
| 16 | **2.616 s** | 40.381 s | 15.4 |
| 32 | 3.563 s | 104.897 s | 29.4 |

Sixteen threads was the CPU-only latency sweet spot. Using all 32 hardware threads made the result 36% slower and consumed far more CPU time. CPU remains a viable faster-than-real-time fallback, but Vulkan has much lower desktop impact.

## Resident-server load

| Requests | Concurrency | Request median | P95 | Aggregate audio speed | Total-system CPU | GPU busy avg/peak | Peak process RSS |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 1 | **0.241 s** | 0.243 s | 45.4x | 4.4% | 56.9% / 82% | 154 MiB |
| 8 | 2 | 0.474 s | 0.480 s | 45.8x | 4.9% | 86.9% / 91% | 193 MiB |
| 8 | 4 | 0.955 s | 0.965 s | 45.4x | 6.5% | 90.2% / 92% | 229 MiB |

There were zero request errors. The server serializes inference against its single model, so concurrent requests queue while total throughput remains around 45x real time. That behavior is appropriate for a one-user dictation shortcut.

The Q5 model occupies 573.4 MB in the Vulkan backend, and its reported working buffers total about 283 MB. Process RSS was 106 MiB idle and 154 MiB during sequential work; Vulkan/unified-memory allocation is not fully represented by Linux process RSS.

## Re-run on the next real recording

The new workflow retains the latest sample at `last-recording.wav`. Run:

```bash
./benchmark-local.sh
```

Or supply any compatible WAV explicitly:

```bash
./benchmark-local.sh /path/to/recording.wav
```
