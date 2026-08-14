# Local Whisper speech-to-text

This directory contains the tracked configuration and scripts for the local
dictation shortcut. Model weights, the `whisper.cpp` checkout/build, recordings,
machine-specific audio settings, and credentials are deliberately ignored by
Git. They must be installed locally after cloning the dotfiles repository.

## Download the model weights

The active configuration uses the `large-v3-turbo` Q5_0 model. From this
directory, download its official `whisper.cpp` GGML conversion:

```bash
mkdir -p models
curl --fail --location --progress-bar \
  --output models/ggml-large-v3-turbo-q5_0.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin
```

That is the only weight required by `transcribe.py`. Confirm that it is in the
expected location:

```bash
ls -lh models/ggml-large-v3-turbo-q5_0.bin
```

The local benchmark also compares Q8_0 and the unquantized model. Download the
optional full model, then derive Q8_0 from it after building the runtime below:

```bash
curl --fail --location --progress-bar \
  --output models/ggml-large-v3-turbo.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin

runtime/whisper.cpp/build-vulkan/bin/whisper-quantize \
  models/ggml-large-v3-turbo.bin \
  models/ggml-large-v3-turbo-q8_0.bin \
  q8_0
```

The downloadable models and upstream download helper are documented in the
[`whisper.cpp` model guide](https://github.com/ggml-org/whisper.cpp/blob/master/models/README.md).

## Install the local runtime

The scripts expect a Vulkan build at
`runtime/whisper.cpp/build-vulkan/bin/whisper-cli`. The resident user service
also uses the corresponding `whisper-server` binary. Set it up with:

```bash
mkdir -p runtime
git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git runtime/whisper.cpp
cmake -S runtime/whisper.cpp -B runtime/whisper.cpp/build-vulkan \
  -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON
cmake --build runtime/whisper.cpp/build-vulkan --config Release -j
```

Vulkan development packages and a working Vulkan driver must already be
installed. See the
[`whisper.cpp` build documentation](https://github.com/ggml-org/whisper.cpp#quick-start)
for CPU-only and other GPU backends.

## Local state

Optionally put a PipeWire source name in `audio_device`; otherwise the default
source is used. Recordings such as `last-recording.wav` remain local and are
never added to Git. The current transcription path is fully local and does not
use `groq_api_key`; that filename remains ignored to prevent an old credential
from being committed accidentally.
