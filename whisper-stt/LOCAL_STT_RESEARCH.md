# Local speech-to-text research for Ryzen AI Max+ 395

Research date: 2026-08-04. Sources are limited to model owners' model cards, official project repositories/documentation, and papers. This note contains no benchmark results for this specific machine; those require running the supplied recording locally.

## Recommendation

For the existing press-to-record / press-to-stop dictation workflow, start with **Whisper large-v3-turbo in `whisper.cpp`, using the Vulkan backend and the Q5_0 model**. Also benchmark the unquantized model once as the accuracy reference. This is the best first implementation because:

- OpenAI describes `turbo` as an optimized `large-v3` with 809M parameters, about 8x the reference large-model speed on its A100 test, and only minimal accuracy degradation. OpenAI cautions that actual speed is hardware-dependent. ([OpenAI Whisper model table](https://github.com/openai/whisper/blob/main/README.md#available-models-and-languages))
- `whisper.cpp` directly supports Linux, x86 CPU inference, integer quantization, Vulkan, and AMD HIP/ROCm. Its official Q5_0 conversion of large-v3-turbo is 547 MiB versus 1.5 GiB for the unquantized model. ([whisper.cpp features and backends](https://github.com/ggml-org/whisper.cpp#whispercpp), [official model list](https://github.com/ggml-org/whisper.cpp/blob/master/models/README.md#available-models))
- The current recorder already emits mono, 16 kHz, signed 16-bit WAV, exactly the form expected by `whisper-cli`; the CLI exposes English selection, thread count, greedy/beam settings, GPU disable for a CPU baseline, and plain/JSON output. ([whisper.cpp CLI options](https://github.com/ggml-org/whisper.cpp/blob/master/examples/cli/README.md))
- Vulkan is the least disruptive GPU route on this Arch/RADV system. `whisper.cpp` calls Vulkan its cross-vendor GPU backend and enables it with `-DGGML_VULKAN=1`. ([Vulkan build instructions](https://github.com/ggml-org/whisper.cpp#vulkan-gpu-support))

For **actual live partial transcripts while the user is still talking**, also benchmark **Moonshine Medium Streaming** before committing to Whisper streaming. Moonshine is purpose-built for incremental speech, caches prior audio computation, has a Python package and Linux x86 library, and its vendor reports 269 ms on its Linux x86 benchmark with 6.65% WER. Those are vendor-published results on different hardware and must be reproduced locally. ([Moonshine official repository and benchmark](https://github.com/moonshine-ai/moonshine#when-should-you-choose-moonshine-over-whisper))

In short: **Whisper.cpp + Vulkan + large-v3-turbo-Q5_0 is the safest replacement for the Groq call now; Moonshine Medium Streaming is the strongest second candidate if “real-time” means stable partial text during speech.**

## Candidate comparison

| Candidate | Accuracy evidence | Latency/streaming characteristics | Support on this machine | Integration fit |
|---|---|---|---|---|
| **Whisper large-v3-turbo + whisper.cpp Vulkan** | OpenAI says turbo is an optimized large-v3 with minimal accuracy degradation. It is multilingual; no `.en` turbo checkpoint exists. | OpenAI reports ~8x relative speed vs large on A100, but this is not a Radeon result. `whisper.cpp` supports offline CLI, a persistent local server, and a “naive” microphone stream example that retranscribes at intervals. | **Direct fit:** Vulkan is officially supported by whisper.cpp and RADV provides the machine's Vulkan path. CPU-only is also supported. | **Best for current toggle.** One local subprocess can replace the network call. A persistent localhost server can keep the model resident and remove per-invocation model-loading latency. |
| **Whisper large-v3-turbo + whisper.cpp CPU** | Same model/decoder; Q5_0 must be checked against the unquantized output because the project does not publish a universal WER penalty for quantization. | Likely comfortably faster than real time on a 16-core Zen 5 CPU, but that is an inference to verify, not an official machine-specific result. | **Direct fit:** whisper.cpp supports x86 AVX and CPU-only inference; OpenBLAS can accelerate the encoder. | Excellent fallback and useful load baseline. It will consume more CPU during transcription than Vulkan. |
| **Moonshine Medium Streaming (245M)** | Moonshine's own cross-model table reports 6.65% WER vs 7.44% for Whisper large-v3 on its chosen OpenASR benchmark. Treat this as a promising vendor claim, not an independent result; it compares against large-v3, not large-v3-turbo. | Designed for live speech: flexible input windows and cached encoder/decoder state. Vendor reports 107 ms Mac and 269 ms Linux x86, with incremental transcript events. | **Direct CPU/Linux fit:** official Python package and prebuilt x86_64 Linux library; portable C++ core uses ONNX Runtime. No Radeon/Vulkan advantage is claimed. | Best architectural fit for genuine streaming. More workflow change than swapping in `whisper-cli`, but still local and the Python API is simple. |
| **faster-whisper / CTranslate2** | It runs Whisper checkpoints, including `turbo`; its project claims up to 4x the OpenAI reference runtime at the same accuracy and supports CPU INT8. | Official 13-minute benchmark on an 8-thread i7-12700K found faster-whisper INT8 faster than whisper.cpp FP32 for `small`, while whisper.cpp FP32 was faster than faster-whisper FP32. This is useful directional evidence only, not a turbo/Ryzen benchmark. | **Easy CPU fit; experimental GPU fit.** Prebuilt CTranslate2 chooses oneDNN on AMD x86. Its published binary/faster-whisper GPU path is NVIDIA, but CTranslate2 4.7 added AMD HIP and a source build exposes `-DWITH_HIP=ON`. That still inherits the ROCm-on-Arch support risk. | Easy Python CPU baseline. A custom HIP build is a second-stage experiment, not the quickest route. ([faster-whisper benchmark](https://github.com/SYSTRAN/faster-whisper#benchmark), [CTranslate2 hardware dispatch](https://opennmt.net/CTranslate2/hardware_support.html), [HIP build option](https://opennmt.net/CTranslate2/installation.html#build-options), [HIP introduction](https://github.com/OpenNMT/CTranslate2/blob/master/CHANGELOG.md#v470-2026-02-03)) |
| **NVIDIA Parakeet Unified English 0.6B** | NVIDIA reports mean WER 5.91 offline and 8.44 at 160 ms streaming latency across its listed OpenASR datasets; it includes punctuation/capitalization. | One checkpoint supports offline and streaming inference down to 160 ms latency. | **Not a practical supported fit:** the official card lists NeMo 2.7.3 and NVIDIA Volta/Ampere/Hopper/Blackwell hardware, not AMD CPU/Vulkan/ROCm. | Attractive model, wrong supported runtime/hardware for this system. Do not make it the first local deployment. ([NVIDIA model card](https://huggingface.co/nvidia/parakeet-unified-en-0.6b)) |
| **OpenAI Whisper Python / Transformers** | Same OpenAI weights; useful reference implementation. | More framework and process overhead than whisper.cpp for a desktop toggle. | PyTorch ROCm can use the 8060S in supported configurations, but the current AMD matrix for this APU does not list Arch. | Keep only as a validation/reference path, not the production toggle. |

### Why not `medium.en` as the default?

OpenAI says English-only checkpoints help most at `tiny.en` and `base.en`, with the difference becoming less significant at `small.en` and `medium.en`. Its table lists `medium` at 769M parameters and ~2x relative speed, while `turbo` is 809M and ~8x, with minimal accuracy degradation. Although those speeds were measured on A100 and must not be transferred directly to Radeon, they make turbo the better first quality/latency tradeoff. Include `small.en` only as a deliberately lower-resource challenger if the local turbo result misses the latency target. ([OpenAI model guidance](https://github.com/openai/whisper/blob/main/README.md#available-models-and-languages))

## Backend choice on this AMD/Arch system

1. **Vulkan/RADV first.** It is supported directly by upstream whisper.cpp, has few moving parts, and matches the already-working graphics stack.
2. **CPU baseline second.** Test both a practical thread count and the full core count; more threads can increase contention without improving single-utterance latency.
3. **HIP/ROCm only as a later experiment.** Upstream whisper.cpp supports `-DGGML_HIP=1`. AMD now identifies the Radeon 8060S as RDNA 3.5 / `gfx1151`, but its published Ryzen support matrix lists Ubuntu releases, not Arch. That makes HIP plausible but operationally higher-risk than Vulkan here. ([whisper.cpp HIP build](https://github.com/ggml-org/whisper.cpp#amd-rocm-gpu-support), [AMD ROCm 7.13 compatibility matrix](https://rocm.docs.amd.com/en/7.13.0-preview/compatibility/compatibility-matrix.html#system-requirements-and-information))
4. **Do not plan around the NPU on Linux yet.** AMD's Whisper.cpp NPU documentation says encoder offload is currently Windows-only and Linux is planned. ([AMD Ryzen AI Whisper.cpp support](https://ryzenai.docs.amd.com/en/1.7/whisper_cpp.html))

The CPU, GPU, and NPU share memory on this APU, so conventional “VRAM used” is less informative than resident memory, GPU busy time, power, and end-to-end latency.

## Integration recommendation

### Lowest-risk first version

Keep the existing `pw-record` toggle and post-stop clipboard/paste behavior. Replace only the Groq transcription function with a local `whisper-cli` invocation, using fixed English, temperature 0, no timestamps, and machine-tested thread/decoder settings. The current 16 kHz mono S16 WAV needs no conversion.

Benchmark the CLI first because it is easy to inspect and fail over. Once correctness is stable, compare it with the official `whisper-server` bound to `127.0.0.1`. The server accepts local multipart WAV requests and keeps the model process resident; this should remove repeated model-load time, though the benefit must be measured. It also ships an official k6 concurrent-load benchmark. ([whisper.cpp server and load test](https://github.com/ggml-org/whisper.cpp/blob/master/examples/server/README.md#load-testing-with-k6))

The server should remain localhost-only and unprivileged. The project explicitly warns against privileged operation and recommends sandboxing because the example accepts uploaded files; do not enable FFmpeg conversion because the recorder already creates the required WAV.

### If continuous transcription is the actual goal

`whisper-stream` samples every half second and continuously reruns transcription; the project itself calls it a naive example. Its VAD mode transcribes on detected silence. This is usable for a prototype but can do redundant work. ([whisper.cpp streaming example](https://github.com/ggml-org/whisper.cpp/blob/master/examples/stream/README.md))

Moonshine is architecturally stronger for continuous partials because it caches prior encoder and decoder state and emits line-started, text-changed, and line-completed events. The official package can be tried with `moonshine-voice mic --language en`. ([Moonshine quickstart and streaming design](https://github.com/moonshine-ai/moonshine#quickstart))

## Benchmark matrix for the supplied recording

Use the exact same WAV and decoding settings for every comparable Whisper run. Report audio duration and:

- **End-to-end stop-to-text latency:** from stopping `pw-record` until final text is ready.
- **Inference-only wall time** and **real-time factor (RTF):** inference seconds divided by audio seconds; RTF below 1 is faster than real time.
- **Cold versus warm:** first run after process/model start, then median and p95 over at least 10 warm runs.
- **Quality:** preserve every transcript and manually compare wording, punctuation, names, commands, and hallucinations. Speed without output quality is not a fair comparison.
- **CPU load:** average and peak total CPU, user/system time, voluntary/involuntary context switches, and peak RSS.
- **GPU/APU load:** GPU busy percentage, clocks, shared-memory use, and package power/temperature if the installed AMD tools expose them.
- **Desktop impact:** note UI stutter and background power; this is more important for dictation than maximum batch throughput.

Run these configurations in order:

1. `large-v3-turbo-q5_0`, Vulkan, greedy (`beam-size=1`, `best-of=1`).
2. `large-v3-turbo` unquantized, Vulkan, same decoder settings.
3. `large-v3-turbo-q8_0`, Vulkan, only if Q5 changes the text materially; the official repository supplies an 874 MB Q8 model. ([official converted-model repository](https://huggingface.co/ggerganov/whisper.cpp/tree/main))
4. Q5_0 CPU-only at sensible thread counts such as 8, 16, and 32; select on measured latency/load, not core count.
5. Optional `small.en` CPU and Vulkan only if turbo is not responsive enough.
6. Moonshine Medium Streaming on CPU, both file transcription and live partial-output latency.
7. Current Groq result for the same WAV, recorded separately as a network baseline (upload + queue + inference + response).

For load testing, desktop dictation is fundamentally a **single-request latency** workload. First run 30 sequential transcriptions and report median/p95 and thermal drift. Then, if a persistent local server may serve multiple clients, test concurrency 2 and 4 and report both request latency and aggregate audio-seconds processed per wall-second. Do not optimize for batch throughput at the expense of the single-user p95.

## Decision rule

Adopt Whisper.cpp Vulkan Q5_0 if it produces the same acceptable text as the unquantized model and its warm stop-to-text p95 feels immediate, ideally under one second for normal short dictation. Use the resident localhost server only if it materially reduces p95 over the CLI. Move to Moonshine Medium Streaming if the desired experience is text updating during speech or if its local transcript is equally good with substantially lower CPU/power. Keep CPU Whisper as the fail-safe; skip Parakeet and the Ryzen NPU until their official Linux/AMD paths match this machine.
