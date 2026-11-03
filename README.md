# AssemblyAI Meeting Transcript Wrapper

A small local wrapper that reads audio files from `input/`, converts each file to mono 16 kHz WAV with FFmpeg, sends it to AssemblyAI for Vietnamese transcription and speaker diarization, and writes JSON files to `output/`.

The output follows the structure in [`MeetingOne_transcript_sample.json`](../MeetingOne_transcript_sample.json): meeting metadata, audio metadata, speakers, and timestamped transcript segments. Speaker names are anonymous labels such as `Speaker A`; AssemblyAI cannot identify real people.

## Requirements

- Python 3.10 or newer
- FFmpeg installed and available as `ffmpeg` on `PATH`
- An AssemblyAI API key
- Internet access while uploading and transcribing

## Setup

Open PowerShell and move into this folder:

```powershell
Set-Location "path\to\assemblyai_meeting_wrapper"
```

Create a virtual environment and install dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Check that FFmpeg is available:

```powershell
ffmpeg -version
```

On first use, the program prompts for your AssemblyAI API key without displaying it and saves it in `.env` in this folder. `.env` is excluded by `.gitignore` and should never be committed.

You can also save or replace the key at any time:

```powershell
.\.venv\Scripts\python.exe meeting_transcriber.py set-key
```

## Transcribe audio

Put supported audio files in `input/` and run:

```powershell
.\.venv\Scripts\python.exe meeting_transcriber.py
```

Supported formats depend on the installed FFmpeg build; common formats include WAV, MP3, M4A, MP4, FLAC, OGG, OPUS, AAC, WMA, and WebM. Each `input/name.ext` produces `output/name.json`. The converted temporary WAV is removed after processing; the original input is kept.

To replace an existing output:

```powershell
.\.venv\Scripts\python.exe meeting_transcriber.py --overwrite
```

To select a meeting date or language explicitly:

```powershell
.\.venv\Scripts\python.exe meeting_transcriber.py --date 2026-10-24 --language vi
```

The defaults are today's date in `Asia/Ho_Chi_Minh` and Vietnamese (`vi`).

## Output format

Each segment contains `segment_id`, `speaker_id`, `start_ms`, `end_ms`, and `text`. Times are milliseconds. Transcript text is UTF-8 and the JSON is written with Vietnamese characters intact. AssemblyAI timestamps and speaker assignments are model estimates; review the result where accuracy matters.

## Commands

```text
python meeting_transcriber.py [--overwrite] [--date YYYY-MM-DD] [--language vi]
python meeting_transcriber.py set-key
```
