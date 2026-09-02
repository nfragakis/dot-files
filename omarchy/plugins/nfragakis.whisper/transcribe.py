#!/usr/bin/env python3
"""Stop, transcribe, and paste a private local Whisper recording."""

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


STATE_DIR = Path(
    os.environ.get(
        "WHISPER_STT_STATE_DIR",
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "whisper-stt",
    )
)
PID_FILE = STATE_DIR / "recording.pid"
RECORDING_FILE = STATE_DIR / "recording.wav"
LAST_AUDIO_FILE = STATE_DIR / "last-recording.wav"

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8178
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}/inference"
SERVER_UNIT = "whisper-stt-local.service"
LOCAL_CLI = STATE_DIR / "runtime" / "whisper.cpp" / "build-vulkan" / "bin" / "whisper-cli"
LOCAL_MODEL = STATE_DIR / "models" / "ggml-large-v3-turbo-q5_0.bin"
LOCAL_VAD_MODEL = STATE_DIR / "models" / "ggml-silero-v6.2.0.bin"


def notify(title, message=""):
    """Send a desktop notification without making transcription depend on it."""
    try:
        subprocess.run(
            ["notify-send", "-a", "Whisper STT", title, message],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass


def is_recording_process(pid):
    """Do not trust a stale PID file enough to signal an unrelated process."""
    try:
        return (Path("/proc") / str(pid) / "comm").read_text().strip() == "pw-record"
    except (FileNotFoundError, PermissionError, OSError):
        return False


def stop_recording():
    """Stop PipeWire cleanly and retain the latest complete WAV."""
    try:
        if not PID_FILE.exists():
            notify("Recording failed", "No recording is in progress")
            return None

        pid = int(PID_FILE.read_text().strip())
        if not is_recording_process(pid):
            PID_FILE.unlink(missing_ok=True)
            notify("Recording failed", "The recording process is no longer running")
            return None

        os.kill(pid, signal.SIGINT)

        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            if not is_recording_process(pid):
                break
            time.sleep(0.03)

        PID_FILE.unlink(missing_ok=True)
        if not RECORDING_FILE.exists() or RECORDING_FILE.stat().st_size <= 44:
            notify("Recording failed", "No audio was captured")
            return None

        os.replace(RECORDING_FILE, LAST_AUDIO_FILE)
        return LAST_AUDIO_FILE
    except (OSError, ValueError) as exc:
        notify("Stop failed", str(exc))
        PID_FILE.unlink(missing_ok=True)
        return None


def server_is_ready(timeout=0.08):
    try:
        with socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_local_server():
    """Start the user service on demand and wait briefly for its local socket."""
    if server_is_ready():
        return True

    try:
        subprocess.run(
            ["systemctl", "--user", "start", SERVER_UNIT],
            check=False,
            timeout=3,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if server_is_ready():
            return True
        time.sleep(0.05)
    return False


def multipart_request(audio_file):
    """Build the multipart request accepted by the loopback server."""
    boundary = f"----whisper-stt-{uuid.uuid4().hex}"
    chunks = []

    def add_field(name, value):
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode(),
                b"\r\n",
            ]
        )

    for name, value in (
        ("temperature", "0.0"),
        ("temperature_inc", "0.2"),
        ("response_format", "json"),
        ("language", "en"),
        ("no_timestamps", "false"),
        ("best_of", "1"),
        ("beam_size", "1"),
    ):
        add_field(name, value)

    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                'Content-Disposition: form-data; name="file"; '
                f'filename="{audio_file.name}"\r\n'
            ).encode(),
            b"Content-Type: audio/wav\r\n\r\n",
            audio_file.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return boundary, b"".join(chunks)


def transcribe_via_server(audio_file):
    boundary, body = multipart_request(audio_file)
    request = urllib.request.Request(
        SERVER_URL,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return " ".join(payload.get("text", "").split())


def transcribe_via_cli(audio_file):
    """Local fallback when the resident server is unavailable."""
    if (
        not LOCAL_CLI.is_file()
        or not LOCAL_MODEL.is_file()
        or not LOCAL_VAD_MODEL.is_file()
    ):
        raise FileNotFoundError("Local Whisper runtime, speech model, or VAD model is missing")

    with tempfile.TemporaryDirectory(prefix="whisper-stt-") as temp_dir:
        output_base = Path(temp_dir) / "transcript"
        subprocess.run(
            [
                str(LOCAL_CLI),
                "-m",
                str(LOCAL_MODEL),
                "-f",
                str(audio_file),
                "-l",
                "en",
                "-t",
                "8",
                "-bs",
                "1",
                "-bo",
                "1",
                "--vad",
                "-vm",
                str(LOCAL_VAD_MODEL),
                "-vp",
                "500",
                "-oj",
                "-of",
                str(output_base),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(output_base.with_suffix(".json").read_text())

    return "".join(segment["text"] for segment in payload["transcription"]).strip()


def transcribe_audio(audio_file):
    """Transcribe entirely on this machine; never call an external API."""
    if ensure_local_server():
        try:
            return transcribe_via_server(audio_file)
        except (OSError, ValueError, KeyError, urllib.error.URLError):
            pass
    return transcribe_via_cli(audio_file)


def copy_to_clipboard(text):
    try:
        subprocess.run(["wl-copy"], input=text.encode(), check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        notify("Clipboard failed", "Could not run wl-copy")
        return False


def paste_at_cursor():
    try:
        time.sleep(0.05)
        subprocess.run(
            ["wtype", "-M", "shift", "-k", "Insert", "-m", "shift"],
            check=True,
            timeout=2,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def main():
    audio_file = stop_recording()
    if not audio_file:
        return 1

    try:
        text = transcribe_audio(audio_file)
    except Exception as exc:
        notify("Local transcription failed", str(exc))
        return 1

    if not text:
        notify("Local transcription failed", "The model returned no text")
        return 1

    if not copy_to_clipboard(text):
        return 1

    paste_at_cursor()
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
