"""Convert local audio and transcribe it with AssemblyAI into MeetingOne JSON."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import dotenv_values, set_key


ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
TEMP_DIR = ROOT / "temp"
ENV_FILE = ROOT / ".env"
TIMEZONE = "Asia/Ho_Chi_Minh"
SUPPORTED_AUDIO = {".wav", ".mp3", ".m4a", ".mp4", ".flac", ".ogg", ".opus", ".aac", ".wma", ".webm"}
UPLOAD_URL = "https://api.assemblyai.com/v2/upload"
TRANSCRIPT_URL = "https://api.assemblyai.com/v2/transcript"


def api_key() -> str:
    """Load the local key or securely prompt and save it on first use."""
    key = os.getenv("ASSEMBLYAI_API_KEY") or dotenv_values(ENV_FILE).get("ASSEMBLYAI_API_KEY")
    if key:
        return key.strip()
    print("AssemblyAI API key not found. It will be saved locally in .env (not committed).")
    print("Key input is hidden while you type or paste; press Enter when done.")
    key = getpass.getpass("AssemblyAI API key: ").strip()
    if not key:
        raise RuntimeError("An API key is required.")
    ENV_FILE.touch(exist_ok=True)
    set_key(str(ENV_FILE), "ASSEMBLYAI_API_KEY", key)
    return key


def set_api_key() -> None:
    print("Key input is hidden while you type or paste; press Enter when done.")
    key = getpass.getpass("New AssemblyAI API key: ").strip()
    if not key:
        raise RuntimeError("The API key cannot be empty.")
    ENV_FILE.touch(exist_ok=True)
    set_key(str(ENV_FILE), "ASSEMBLYAI_API_KEY", key)
    print(f"API key saved to {ENV_FILE}.")


def run_ffmpeg(source: Path, destination: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg was not found. Install it and make sure ffmpeg is on PATH.")
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destination)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"FFmpeg could not convert {source.name}: {(exc.stderr or '').strip()}") from exc


def make_text(text: str) -> str:
    text = " ".join(text.split()).strip()
    if text and text[-1] not in ".!?…。！？":
        text += "."
    return text


def poll_transcript(session: requests.Session, transcript_id: str) -> dict:
    last_status = None
    while True:
        response = session.get(f"{TRANSCRIPT_URL}/{transcript_id}", timeout=60)
        response.raise_for_status()
        result = response.json()
        status = result.get("status")
        if status != last_status:
            print(f"  Transcript status: {status}", flush=True)
            last_status = status
        if status == "completed":
            return result
        if status == "error":
            raise RuntimeError(result.get("error", "AssemblyAI transcription failed."))
        time.sleep(3)


def transcribe_file(source: Path, destination: Path, key: str, meeting_date: str, language: str, overwrite: bool) -> None:
    if destination.exists() and not overwrite:
        print(f"Skipping {source.name}: {destination.name} already exists (use --overwrite to replace).")
        return
    TEMP_DIR.mkdir(exist_ok=True)
    normalized = TEMP_DIR / f"{source.stem}_mono_16k.wav"
    headers = {"Authorization": key}
    session = requests.Session()
    session.headers.update(headers)
    try:
        print(f"Converting {source.name} to mono 16 kHz WAV...")
        run_ffmpeg(source, normalized)
        print("Uploading normalized audio...")
        with normalized.open("rb") as audio_file:
            upload = session.post(UPLOAD_URL, data=audio_file, headers={"Content-Type": "application/octet-stream"}, timeout=(30, 1800))
        upload.raise_for_status()
        body = {
            "audio_url": upload.json()["upload_url"],
            "speech_models": ["universal-3-5-pro"],
            "language_code": language,
            "speaker_labels": True,
            "punctuate": True,
            "format_text": True,
        }
        submitted = session.post(TRANSCRIPT_URL, json=body, timeout=60)
        submitted.raise_for_status()
        result = poll_transcript(session, submitted.json()["id"])
        utterances = result.get("utterances") or []
        if not utterances:
            raise RuntimeError("Transcription completed without diarized utterances; no output was written.")

        speaker_map: dict[str, str] = {}
        segments = []
        for utterance in utterances:
            raw = utterance.get("speaker")
            label = str(raw) if raw is not None else "unknown"
            speaker_map.setdefault(label, f"spk_{len(speaker_map) + 1:02d}")
            segments.append({
                "segment_id": f"seg_{len(segments) + 1:04d}",
                "speaker_id": speaker_map[label],
                "start_ms": int(utterance["start"]),
                "end_ms": int(utterance["end"]),
                "text": make_text(utterance.get("text", "")),
            })
        duration = result.get("audio_duration") or 0
        lang = result.get("language_code") or language
        normalized_language = "vi-VN" if lang.lower().startswith("vi") else lang
        document = {
            "format_version": "1.0.0",
            "meeting_id": source.stem,
            "meeting_date": meeting_date,
            "timezone": TIMEZONE,
            "audio": {"file_name": source.name, "duration_ms": round(float(duration) * 1000), "language": normalized_language},
            "speakers": [{"speaker_id": speaker_id, "display_name": f"Speaker {label}" if label != "unknown" else "Unknown"} for label, speaker_id in speaker_map.items()],
            "segments": segments,
        }
        OUTPUT_DIR.mkdir(exist_ok=True)
        destination.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved {len(segments)} segments to {destination.relative_to(ROOT)}")
    finally:
        normalized.unlink(missing_ok=True)
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe input audio into MeetingOne-compatible JSON using AssemblyAI.")
    parser.add_argument("command", nargs="?", choices=("set-key",), help="Use 'set-key' to add or replace the saved API key.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing output JSON files.")
    parser.add_argument("--date", default=None, help="Meeting date in YYYY-MM-DD format (default: today in the configured timezone).")
    parser.add_argument("--language", default="vi", help="AssemblyAI language code (default: vi).")
    args = parser.parse_args()
    try:
        if args.command == "set-key":
            set_api_key()
            return 0
        meeting_date = args.date or datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()
        date.fromisoformat(meeting_date)
        INPUT_DIR.mkdir(exist_ok=True)
        files = sorted(path for path in INPUT_DIR.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO)
        if not files:
            print(f"No supported audio files found in {INPUT_DIR}.")
            return 0
        key = api_key()
        OUTPUT_DIR.mkdir(exist_ok=True)
        for source in files:
            try:
                transcribe_file(source, OUTPUT_DIR / f"{source.stem}.json", key, meeting_date, args.language, args.overwrite)
            except (OSError, requests.RequestException, KeyError, ValueError, RuntimeError) as exc:
                print(f"Failed to process {source.name}: {exc}", file=sys.stderr)
                return 1
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
