# Whisper Dictation

A panel-only Omarchy plugin for private local dictation. It has no bar widget
and adds nothing to the sidebar. While recording, a click-through popup at the
top center of the screen shows a live waveform from the selected PipeWire source.
After recording stops, the popup shows transcription progress until the text is
copied and pasted at the cursor.

The plugin owns the shortcut-facing recording and transcription code. Large
model weights, the compiled `whisper.cpp` runtime, recordings, and the optional
machine-specific audio source remain outside git in
`~/.config/whisper-stt/`.

## Install the plugin

From the dot-files root:

```bash
./install-omarchy.sh
omarchy/plugins/nfragakis.whisper/install.sh
```

The first command links the plugin into Omarchy. The second links its hardened
on-demand user service and reloads the user systemd manager. The plugin is
enabled by the tracked `omarchy/shell.json`; it does not need a bar entry.

`Super + Shift + L` starts recording. Press it again to stop, transcribe, and
paste. The same actions are available over shell IPC:

```bash
omarchy-shell whisper-stt start
omarchy-shell whisper-stt stop
omarchy-shell whisper-stt toggle
omarchy-shell whisper-stt status
```

## Download the model weights

The active configuration uses the `large-v3-turbo` Q5_0 speech model plus the
Silero v6.2.0 voice-activity detector. VAD prevents Whisper from treating long
pauses as speech and looping on its most recent phrase.

```bash
state_dir="${XDG_CONFIG_HOME:-$HOME/.config}/whisper-stt"
mkdir -p "$state_dir/models"

curl --fail --location --progress-bar \
  --output "$state_dir/models/ggml-large-v3-turbo-q5_0.bin" \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin

curl --fail --location --progress-bar \
  --output "$state_dir/models/ggml-silero-v6.2.0.bin" \
  https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v6.2.0.bin
```

## Build the local runtime

The plugin expects Vulkan binaries at
`~/.config/whisper-stt/runtime/whisper.cpp/build-vulkan/bin/`:

```bash
state_dir="${XDG_CONFIG_HOME:-$HOME/.config}/whisper-stt"
mkdir -p "$state_dir/runtime"
git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git \
  "$state_dir/runtime/whisper.cpp"
cmake \
  -S "$state_dir/runtime/whisper.cpp" \
  -B "$state_dir/runtime/whisper.cpp/build-vulkan" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_VULKAN=ON
cmake --build "$state_dir/runtime/whisper.cpp/build-vulkan" \
  --config Release -j
```

Vulkan development packages and a working Vulkan driver must already be
installed. The
[`whisper.cpp` build documentation](https://github.com/ggml-org/whisper.cpp#quick-start)
covers CPU-only and other GPU backends, but the tracked service currently uses
the Vulkan build path above.

## Select a microphone

By default both recording and the waveform use PipeWire's default source. To
pin a source, write its PipeWire node name to:

```text
~/.config/whisper-stt/audio_device
```

The recording backend always honors that value. The waveform uses the same
source when Quickshell can resolve the node name, and otherwise falls back to
the current default source.

The full transcription path is local. No recording or transcript is sent to
an external API.
