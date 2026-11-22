import subprocess
import sys
from types import SimpleNamespace
import unittest

import src.utils
from unittest.mock import patch

from src.gpu import GPUDisplayHelper, GPUManager
from src.utils.gpu import GPUInfo, GPUType
from src.utils.gpu.nvidia import get_nvidia_gpus


def gpu(index, name="same GPU", bus="00000000:0A:00.0"):
    return GPUInfo(index, name, GPUType.NVIDIA, 8 * 2**30, pci_bus_id=bus)


class GpuIdentityTests(unittest.TestCase):
    def test_zero_index_and_zero_free_memory_are_not_lost_during_merge(self):
        current = gpu(2)
        current.avail_dedicated_gpu_memory = 100
        update = gpu(0)
        update.avail_dedicated_gpu_memory = 0
        current.merge_from(update)
        self.assertEqual(current.index, 0)
        self.assertEqual(current.avail_dedicated_gpu_memory, 0)

    def test_same_name_gpu_uses_device_index_not_position_in_name_subset(self):
        infos = {"other": gpu(0, "different"), "first": gpu(1), "second": gpu(2)}
        self.assertEqual(GPUDisplayHelper.find_gpu_key("same GPU (GPU 2)", infos), "second")

    def test_nvidia_query_preserves_authoritative_index_and_uuid(self):
        result = subprocess.CompletedProcess([], 0, "0, GPU-abcd, NVIDIA GeForce RTX 4060 Laptop GPU, 00000000:0A:00.0, 7000 MiB, 8192 MiB\n", "")
        with patch("src.utils.gpu.nvidia.subprocess.run", return_value=result):
            rows = get_nvidia_gpus()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].index, 0)
        self.assertEqual(rows[0].uuid, "GPU-abcd")

    def test_display_index_does_not_come_from_pci_bus_number(self):
        with patch.object(GPUManager, "detect_gpus"):
            manager = GPUManager()
        with patch("src.gpu.get_nvidia_gpus", return_value=[gpu(0)]):
            manager._GPUManager__universal_detect_nvidia_gpu()
        self.assertEqual(manager.nvidia_gpus, ["same GPU (GPU 0)"])

    def test_registry_adapters_without_pci_ids_do_not_collapse_into_none_key(self):
        adapters = [SimpleNamespace(AdapterString=name, MemorySize=8 * 2**30, pci_bus_id=None)
                    for name in ["AMD first", "AMD second"]]
        windows = SimpleNamespace(get_gpu_mem_info=lambda: adapters)
        wmi = SimpleNamespace(WMI=lambda: SimpleNamespace(Win32_VideoController=lambda: []))
        with patch.object(GPUManager, "detect_gpus"):
            manager = GPUManager()
        with patch.object(src.utils, "windows", windows, create=True), patch.dict(sys.modules, {"wmi": wmi}), patch("src.gpu.get_nvidia_gpus", return_value=[]):
            manager.detect_gpus_windows()
        self.assertEqual(set(manager.gpu_info_map), {"AMD first", "AMD second"})

    def test_nvidia_visibility_uses_uuid_not_combobox_position(self):
        with patch.object(GPUManager, "detect_gpus"):
            manager = GPUManager()
        info = gpu(2)
        info.uuid = "GPU-abcd"
        manager.gpu_info_map = {"key": info}
        result = manager.set_gpu_env({}, "same GPU (GPU 2)", 0)
        self.assertEqual(result["CUDA_VISIBLE_DEVICES"], "GPU-abcd")
