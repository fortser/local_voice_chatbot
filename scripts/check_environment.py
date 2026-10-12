"""Проверка окружения «Шурочки» после установки зависимостей.

Запуск из корня проекта (его вызывает ``install_and_test.bat``):

    python scripts/check_environment.py            # основное окружение
    python scripts/check_environment.py --gigaam   # + зависимости GigaAM-v3

Что проверяется:
  * версия Python (проект рассчитан на 3.10–3.11);
  * наличие и версии ключевых пакетов (без тяжёлого импорта TTS);
  * numpy 1.x (2.x ломает синтез речи и Whisper);
  * PyTorch: CUDA-сборка и доступность видеокарты для настроек из settings.toml;
  * settings.toml читается без ошибок;
  * Silero VAD на настоящей модели: тишина отсекается, а ваша запись речи
    из logs/stage9/take1_raw.wav (если есть) проходит.

Код выхода: 0 — обязательное в порядке (предупреждения допустимы), 1 — ошибки.
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# (модуль для импорта, пакет pip)
REQUIRED = [
    ("numpy", "numpy"),
    ("torch", "torch"),
    ("whisper", "openai-whisper"),
    ("TTS", "coqui-tts"),
    ("transformers", "transformers"),
    ("sounddevice", "sounddevice"),
    ("soundfile", "soundfile"),
    ("librosa", "librosa"),
    ("df", "deepfilternet"),
    ("pydantic", "pydantic"),
    ("tomli_w", "tomli-w"),
    ("PySide6", "PySide6"),
    ("silero_vad", "silero-vad"),
    ("mss", "mss"),
    ("pycaw", "pycaw"),
    ("pystray", "pystray"),
    ("pynput", "pynput"),
    ("pyautogui", "pyautogui"),
    ("cv2", "opencv-python"),
    ("pytest", "pytest"),
    ("pytest_mock", "pytest-mock"),
]

GIGAAM = [
    ("transformers", "transformers"),
    ("torchaudio", "torchaudio"),
    ("hydra", "hydra-core"),
    ("omegaconf", "omegaconf"),
    ("sentencepiece", "sentencepiece"),
]


class Report:
    def __init__(self) -> None:
        self.errors = 0
        self.warnings = 0

    def ok(self, text: str) -> None:
        print(f"  [ OK ] {text}")

    def warn(self, text: str) -> None:
        self.warnings += 1
        print(f"  [WARN] {text}")

    def fail(self, text: str) -> None:
        self.errors += 1
        print(f"  [FAIL] {text}")


def version_of(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "?"


def check_packages(report: Report, packages, *, required: bool) -> None:
    for module, dist in packages:
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        if found:
            report.ok(f"{dist} {version_of(dist)}")
        elif required:
            report.fail(f"{dist} не установлен")
        else:
            report.warn(f"{dist} не установлен")


def check_python(report: Report) -> None:
    major, minor = sys.version_info[:2]
    text = f"Python {major}.{minor} ({sys.executable})"
    if (major, minor) in {(3, 10), (3, 11)}:
        report.ok(text)
    else:
        report.warn(text + " — проект рассчитан на 3.10–3.11")


def check_numpy(report: Report) -> None:
    try:
        import numpy
    except ImportError:
        return
    if numpy.__version__.startswith("1."):
        report.ok(f"numpy {numpy.__version__} (ветка 1.x, как в requirements.txt)")
    else:
        report.fail(f"numpy {numpy.__version__}: нужен 1.26.x — pip install numpy==1.26.4")


def load_project_settings(report: Report):
    try:
        from config import settings
    except Exception as exc:
        report.fail(f"settings.toml не читается: {exc}")
        return None
    report.ok("settings.toml прочитан")
    return settings


def check_torch(report: Report, settings) -> None:
    try:
        import torch
    except Exception as exc:
        report.fail(f"PyTorch не импортируется: {exc}")
        return
    cuda = torch.version.cuda
    if cuda is None:
        report.warn(f"PyTorch {torch.__version__} — сборка БЕЗ CUDA, модели будут работать на процессоре")
    elif torch.cuda.is_available():
        report.ok(f"PyTorch {torch.__version__}, CUDA {cuda}, видеокарта: {torch.cuda.get_device_name(0)}")
    else:
        report.warn(f"PyTorch {torch.__version__} с CUDA {cuda}, но видеокарта недоступна — проверьте драйвер NVIDIA")
    if settings is None:
        return
    wanted = {
        "Whisper": settings.stt.whisper_device,
        "GigaAM": settings.stt.gigaam.device if settings.stt.provider.lower() == "gigaam" else "cpu",
    }
    if not torch.cuda.is_available():
        for name, device in wanted.items():
            if str(device).lower().startswith("cuda"):
                report.fail(f"{name} настроен на {device}, но CUDA недоступна — "
                            f'установите CUDA-сборку PyTorch или задайте device = "cpu" в settings.toml')


def check_speech_gate(report: Report) -> None:
    try:
        import numpy as np
        import soundfile as sf

        from config_model import SpeechGateSettings
        from core.speech_gate import SpeechGate
    except Exception as exc:
        report.fail(f"модуль фильтра речи не импортируется: {exc}")
        return
    gate = SpeechGate(SpeechGateSettings())
    if not gate.preload():
        report.fail(f"Silero VAD не загрузился: {gate.unavailable_reason}")
        return
    report.ok("Silero VAD загружен")
    with tempfile.TemporaryDirectory(prefix="shura-check-") as directory:
        silence = Path(directory) / "silence.wav"
        noise = (np.random.default_rng(1).standard_normal(16000 * 3) * 0.002).astype(np.float32)
        sf.write(silence, noise, 16000, subtype="PCM_16")
        result = gate.filter_file(silence)
        if result.has_speech:
            report.warn(f"Silero нашёл речь в тихом шуме ({result.speech_ms:.0f} мс) — "
                        "попробуйте повысить [speech_gate] threshold")
        else:
            report.ok("тишина отсечена до распознавания")
    # tests/fixtures/sample.wav — синтетический тон, не речь; эталон — ваша запись.
    sample = ROOT / "logs" / "stage9" / "take1_raw.wav"
    if not sample.is_file():
        report.ok("эталонной записи речи logs/stage9/take1_raw.wav нет — проверка речи пропущена")
        return
    result = gate.filter_file(sample)
    if result.has_speech:
        report.ok(f"речь в {sample.relative_to(ROOT)} найдена: {result.speech_ms:.0f} мс "
                  f"из {result.duration_ms:.0f} мс")
        from core.speech_gate import discard

        discard(result)
    else:
        report.fail(f"в записи речи {sample.relative_to(ROOT)} фильтр речи ничего не нашёл — "
                    "понизьте [speech_gate] threshold в settings.toml")


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка окружения «Шурочки»")
    parser.add_argument("--gigaam", action="store_true", help="проверить зависимости GigaAM-v3")
    args = parser.parse_args()
    report = Report()

    print("\n== Python и пакеты ==")
    check_python(report)
    check_packages(report, REQUIRED, required=True)
    check_numpy(report)

    if args.gigaam:
        print("\n== GigaAM-v3 (опционально) ==")
        check_packages(report, GIGAAM, required=True)

    print("\n== Настройки и видеокарта ==")
    settings = load_project_settings(report)
    if settings is not None:
        report.ok(f"модель распознавания: {settings.stt.provider}; фильтр речи: "
                  f"{'вкл' if settings.speech_gate.enabled else 'выкл'}; очистка галлюцинаций: "
                  f"{'вкл' if settings.stt.filter.enabled else 'выкл'}")
    check_torch(report, settings)

    print("\n== Фильтр речи на настоящей модели ==")
    check_speech_gate(report)

    print(f"\nИтог: ошибок {report.errors}, предупреждений {report.warnings}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
