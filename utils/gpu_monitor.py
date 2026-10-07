"""NVML telemetry for the whole NVIDIA device, independent of torch/CUDA."""

from __future__ import annotations


class GPUMonitor:
    def __init__(self, nvml=None) -> None:
        self._nvml = nvml
        self._initialized = False

    def snapshot(self) -> dict:
        try:
            if self._nvml is None:
                import pynvml
                self._nvml = pynvml
            nvml = self._nvml
            if not self._initialized:
                nvml.nvmlInit()
                self._initialized = True
            devices = []
            for index in range(nvml.nvmlDeviceGetCount()):
                handle = nvml.nvmlDeviceGetHandleByIndex(index)
                name = nvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")
                row = {"index": index, "name": name, "utilization": None,
                       "memory_used": None, "memory_total": None}
                try:
                    row["utilization"] = nvml.nvmlDeviceGetUtilizationRates(handle).gpu
                except Exception:
                    pass
                try:
                    memory = nvml.nvmlDeviceGetMemoryInfo(handle)
                    row.update(memory_used=memory.used, memory_total=memory.total)
                except Exception:
                    pass
                devices.append(row)
            return {"devices": devices, "error": None if devices else "Видеокарты NVIDIA не обнаружены"}
        except ImportError:
            return {"devices": [], "error": "Установите nvidia-ml-py из requirements.txt"}
        except Exception:
            return {"devices": [], "error": "Мониторинг недоступен: проверьте драйвер NVIDIA"}

    def close(self) -> None:
        if self._initialized:
            try:
                self._nvml.nvmlShutdown()
            finally:
                self._initialized = False
