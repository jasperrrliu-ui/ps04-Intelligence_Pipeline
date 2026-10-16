# YouTube and podcast collection setup

Install the Python packages in `requirements.txt`. The YouTube collector uses `yt-dlp` for video metadata, comments, and subtitles. Podcast episodes are discovered from their RSS audio enclosures. Extraction tries publisher subtitles or transcripts first, then local audio transcription.

For sources without text, install [FFmpeg](https://ffmpeg.org/download.html), a [whisper.cpp `whisper-cli` binary](https://github.com/ggml-org/whisper.cpp/releases), and an English [GGML Whisper model](https://huggingface.co/ggerganov/whisper.cpp/tree/main). Set these environment variables before running the extraction stage:

| Variable | Purpose |
| --- | --- |
| `FFMPEG_BIN` | Absolute path to `ffmpeg.exe`, or omit when `ffmpeg` is on `PATH`. |
| `WHISPER_BIN` | Absolute path to `whisper-cli.exe`, or omit when it is on `PATH`. |
| `WHISPER_MODEL` | Absolute path to a compatible `ggml-*.bin` model. Required for audio transcription. |
| `WHISPER_THREADS` | Optional CPU thread count; default `4`. |
| `PYTHON_BIN` | Python command used by the Bash entry points; default `python3`. |

The pipeline retains original audio under `data/media/`, transcript text under `data/assets/`, and a JSON array of timestamped segments for every media item. A missing transcript or transcription tool is an incomplete extraction, not an empty result. Automated transcripts have `transcription_verified: false` until a person checks passages against the recording. Comments are supplementary audience feedback and do not count as independent source items.
