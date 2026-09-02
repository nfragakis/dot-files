#!/usr/bin/env python3
"""Manual regression check for phrase loops in long Whisper recordings."""

import re
import subprocess
import sys
import tempfile
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

import transcribe  # noqa: E402


REFERENCE_AUDIO = (
    transcribe.STATE_DIR / "runtime" / "whisper.cpp" / "samples" / "jfk.mp3"
)


def find_repeated_phrase(text, repetitions=3):
    words = re.findall(r"[a-z']+", text.lower())
    for width in range(2, 13):
        for start in range(len(words) - repetitions * width + 1):
            phrase = words[start : start + width]
            if all(
                words[start + repeat * width : start + (repeat + 1) * width]
                == phrase
                for repeat in range(1, repetitions)
            ):
                return " ".join(phrase)
    return None


def transcribe_silence_fixture():
    if not REFERENCE_AUDIO.is_file():
        raise FileNotFoundError(f"Reference audio is missing: {REFERENCE_AUDIO}")

    with tempfile.TemporaryDirectory(prefix="whisper-long-recording-") as temp_dir:
        test_audio = Path(temp_dir) / "speech-then-silence.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(REFERENCE_AUDIO),
                "-f",
                "lavfi",
                "-t",
                "180",
                "-i",
                "anullsrc=r=16000:cl=mono",
                "-filter_complex",
                "[0:a][1:a]concat=n=2:v=0:a=1[out]",
                "-map",
                "[out]",
                "-c:a",
                "pcm_s16le",
                str(test_audio),
            ],
            check=True,
        )
        return transcribe.transcribe_audio(test_audio)


def main():
    if len(sys.argv) > 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} [audio-file]")

    if len(sys.argv) == 2:
        text = transcribe.transcribe_audio(Path(sys.argv[1]))
        expected_phrase = None
    else:
        text = transcribe_silence_fixture()
        expected_phrase = "fellow americans"

    if expected_phrase and expected_phrase not in text.lower():
        raise AssertionError(f"Reference speech was not preserved: {text!r}")
    if "\n" in text or "\r" in text:
        raise AssertionError(f"Transcript contains unexpected line breaks: {text!r}")

    repeated_phrase = find_repeated_phrase(text)
    if repeated_phrase:
        raise AssertionError(
            f"Model looped a phrase three times: {repeated_phrase!r}\n{text}"
        )

    print("PASS: single-line speech preserved; no phrase looped three times")


if __name__ == "__main__":
    main()
