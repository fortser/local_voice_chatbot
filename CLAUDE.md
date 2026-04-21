# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the assistant

```bash
# Default: Tkinter GUI with diagnostics panel
python main.py

# Interactive REPL + IPC server
python main.py --mode console

# Headless IPC server only
python main.py --mode ipc

# Suppress IPC server in console mode
python main.py --mode console --no-ipc
```

## Stage validation scripts

Every completed stage has a `check_stage_<N>.py` in the project root. These are **standalone manual-verification scripts** — not automated tests. Run them like:

```bash
python check_stage_7.py
```

Each script prints a checklist, runs the relevant subsystem, and asks for y/n acceptance. A stage is not done until the user accepts it via this script. Scripts are deleted after acceptance.

## Running tests

```bash
pytest
# Single test file:
pytest tests/test_something.py
```

## Environment

- Python 3.10, CUDA 12.x, Windows 10
- Install deps: `pip install -r requirements.txt`
- LLM backend must be running externally: Ollama (`http://localhost:11434`) or LM Studio (`http://localhost:1234`)
- List audio devices: `python -m utils.audio_devices`
- List XTTS speakers: `python -m utils.tts_speakers`

## Architecture

The pipeline is `AudioStream → VAD → STT → LLM → TTS → AudioPlayer`, orchestrated by `VoicePipeline` in `main.py`.

**Entry points:**
- `main.py` — console/IPC/UI orchestrator; `VoicePipeline` owns all subsystems and a shared `threading.Lock` so console turns and IPC calls can't overlap
- `ui/tkinter_ui.py` — wraps `VoicePipeline`; the pipeline runs on a background worker thread, UI in the main thread
- `check_stage_<N>.py` — standalone stage validators (temporary)

**Provider pattern:**
All subsystems use abstract base classes in `core/base.py` (`STTProvider`, `LLMProvider`, `TTSProvider`). Concrete implementations are in `core/`; `core/__init__.py` exports factory functions (`create_stt_provider`, `create_llm_provider`, `create_tts_provider`) that read `config.py` and instantiate the right class. Adding a new backend = implement the ABC + register in the factory dict, no changes to orchestration code.

**IPC layer (`ipc/`):**
Line-delimited JSON over TCP (default `127.0.0.1:9999`). `ipc/server.py` runs in a daemon thread; `ipc/client.py` is the sync client (one connection per call). `ipc/schemas.py` defines Pydantic request/response models; `ipc/protocol.py` handles framing and error codes. IPC methods: `health_check`, `generate_only`, `transcribe_and_respond`, `recalibrate`.

**GPU VRAM swap:**
Whisper (STT) runs on CUDA. Silero TTS runs on CPU — both coexist. XTTS on CUDA fights Whisper for VRAM, so `VoicePipeline` detects this at startup and does unload-STT → load-TTS → synth → unload-TTS → reload-STT on every turn when `TTS_PROVIDER=xtts` and `TTS_DEVICE=cuda`.

**Audio devices:**
The app never pins devices — it reads Windows system defaults and prints them at startup via `bootstrap()`. Users change devices in Windows Sound Settings. `bootstrap()` must be called at the top of every entry point and every `check_stage_<N>.py`.

**Configuration:**
All tunables in `config.py`. Key switches: `TTS_PROVIDER` (`silero`/`xtts`), `LLM_PROVIDER` (`lmstudio`/`ollama`), `WHISPER_DEVICE`, `SILERO_DEVICE`/`TTS_DEVICE`.

**LLM system prompt:**
The system prompt (`LLM_SYSTEM_PROMPT` in `config.py`) is Russian-only, plain text, no markdown — because the TTS engine (Silero) breaks on Latin characters, emoji, and markup. Thinking models are auto-detected via `core/prompt_manager.py` and get a 3× token budget (`OLLAMA_MAX_TOKENS_THINKING_MULTIPLIER`).

**Logging:**
Structured via `logging_config.py`. Log file: `logs/voice_ai.log` (rotating, 5 MB × 3). TTS output WAVs saved to `logs/tts_out/`.
