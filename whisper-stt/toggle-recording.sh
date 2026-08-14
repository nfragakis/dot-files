#!/bin/bash
# Fast local-only recording toggle; Python starts only when recording stops.

STATE_DIR="$HOME/.config/whisper-stt"
PID_FILE="$STATE_DIR/recording.pid"
AUDIO_FILE="$STATE_DIR/recording.wav"
DEVICE_CONFIG="$STATE_DIR/audio_device"

if [ -f "$PID_FILE" ]; then
    # Already recording - stop and transcribe
    python "$STATE_DIR/transcribe.py"
else
    # Not recording - start immediately
    rm -f "$AUDIO_FILE"

    # Warm the local model while the user is speaking.
    systemctl --user start whisper-stt-local.service >/dev/null 2>&1 &

    # Load device config if it exists
    RECORD_ARGS=(--channels=1 --rate=16000 --format=s16)
    if [ -f "$DEVICE_CONFIG" ]; then
        DEVICE=$(tr -d '[:space:]' < "$DEVICE_CONFIG")
        if [ -n "$DEVICE" ]; then
            RECORD_ARGS+=(--target "$DEVICE")
        fi
    fi
    RECORD_ARGS+=("$AUDIO_FILE")

    # Start recording in background (immediate!)
    pw-record "${RECORD_ARGS[@]}" >/dev/null 2>&1 &

    # Save PID
    echo $! > "$PID_FILE"

    # Show notification (async, doesn't block)
    notify-send -a "Whisper STT" "🎙️ Recording started" "Press SUPER+SHIFT+L again to stop" &
fi
