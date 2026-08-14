#!/bin/bash
set -euo pipefail

STATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUDIO="${1:-$STATE_DIR/last-recording.wav}"
RUNS="${RUNS:-5}"
SERVER_URL="http://127.0.0.1:8178/inference"
VULKAN_CLI="$STATE_DIR/runtime/whisper.cpp/build-vulkan/bin/whisper-cli"
CPU_CLI="$STATE_DIR/runtime/whisper.cpp/build-cpu/bin/whisper-cli"
SAMPLE_FALLBACK="$STATE_DIR/runtime/whisper.cpp/samples/jfk.wav"

if [ ! -f "$AUDIO" ] && [ "$AUDIO" = "$STATE_DIR/last-recording.wav" ]; then
    AUDIO="$SAMPLE_FALLBACK"
fi
if [ ! -f "$AUDIO" ]; then
    echo "Audio file not found: $AUDIO" >&2
    exit 1
fi

DURATION=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$AUDIO")
echo "audio,$AUDIO"
echo "duration_seconds,$DURATION"
echo "kind,configuration,run,wall_seconds,user_cpu_seconds,system_cpu_seconds"

for spec in \
    "q5 $STATE_DIR/models/ggml-large-v3-turbo-q5_0.bin" \
    "q8 $STATE_DIR/models/ggml-large-v3-turbo-q8_0.bin" \
    "full $STATE_DIR/models/ggml-large-v3-turbo.bin"
do
    read -r label model <<< "$spec"
    for run in $(seq 1 "$RUNS"); do
        TIMEFORMAT="cli-vulkan,$label,$run,%R,%U,%S"
        { time "$VULKAN_CLI" -m "$model" -f "$AUDIO" -l en -t 8 \
            -bs 1 -bo 1 -nf -nt -np >/dev/null 2>&1; } 2>&1
    done
done

for threads in 4 8 16 32; do
    TIMEFORMAT="cli-cpu,q5-t$threads,1,%R,%U,%S"
    { time "$CPU_CLI" -m "$STATE_DIR/models/ggml-large-v3-turbo-q5_0.bin" \
        -f "$AUDIO" -l en -t "$threads" -bs 1 -bo 1 -nf -nt -np \
        >/dev/null 2>&1; } 2>&1
done

systemctl --user start whisper-stt-local.service
for attempt in $(seq 1 100); do
    if curl -fsS "http://127.0.0.1:8178/" >/dev/null 2>&1; then
        break
    fi
    sleep 0.05
done

echo "kind,configuration,run,wall_seconds"
for run in $(seq 1 10); do
    curl -fsS -o /dev/null -w "server,sequential,$run,%{time_total}\n" \
        "$SERVER_URL" -F "file=@$AUDIO" -F temperature=0.0 \
        -F temperature_inc=0.0 -F response_format=json -F language=en \
        -F no_timestamps=true -F best_of=1 -F beam_size=1
done

export AUDIO SERVER_URL
for concurrency in 2 4; do
    seq 1 8 | xargs -P "$concurrency" -I{} bash -c '
        curl -fsS -o /dev/null \
            -w "server,concurrency-'"$concurrency"',{},%{time_total}\n" \
            "$SERVER_URL" -F "file=@$AUDIO" -F temperature=0.0 \
            -F temperature_inc=0.0 -F response_format=json -F language=en \
            -F no_timestamps=true -F best_of=1 -F beam_size=1
    '
done
