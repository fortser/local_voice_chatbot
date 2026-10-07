from types import SimpleNamespace
from unittest.mock import Mock

from utils.gpu_monitor import GPUMonitor


def nvml():
    return SimpleNamespace(
        nvmlInit=Mock(), nvmlShutdown=Mock(), nvmlDeviceGetCount=lambda: 2,
        nvmlDeviceGetHandleByIndex=lambda index: index,
        nvmlDeviceGetName=lambda handle: f"GPU {handle}".encode(),
        nvmlDeviceGetUtilizationRates=Mock(return_value=SimpleNamespace(gpu=0)),
        nvmlDeviceGetMemoryInfo=Mock(return_value=SimpleNamespace(used=2**30, total=8 * 2**30)),
    )


def test_multiple_cards_zero_load_and_nvml_lifecycle():
    library = nvml()
    monitor = GPUMonitor(library)
    result = monitor.snapshot()
    assert len(result["devices"]) == 2
    assert result["devices"][0]["utilization"] == 0
    assert result["devices"][1]["memory_used"] == 2**30
    assert result["devices"][1]["name"] == "GPU 1"
    monitor.snapshot()
    library.nvmlInit.assert_called_once()
    monitor.close()
    monitor.close()
    library.nvmlShutdown.assert_called_once()


def test_metrics_fail_independently():
    library = nvml()
    library.nvmlDeviceGetUtilizationRates.side_effect = RuntimeError("not supported")
    result = GPUMonitor(library).snapshot()["devices"][0]
    assert result["utilization"] is None
    assert result["memory_total"] == 8 * 2**30
    library.nvmlDeviceGetMemoryInfo.side_effect = RuntimeError("not supported")
    assert GPUMonitor(library).snapshot()["devices"][0]["memory_used"] is None


def test_driver_unavailable_is_not_zero_load():
    library = nvml()
    library.nvmlInit.side_effect = RuntimeError("no driver")
    result = GPUMonitor(library).snapshot()
    assert result["devices"] == [] and result["error"]


def test_missing_package(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "pynvml", None)
    assert "nvidia-ml-py" in GPUMonitor().snapshot()["error"]
