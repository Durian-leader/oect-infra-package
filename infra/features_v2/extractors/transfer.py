"""
Transfer 特征提取器

基于 oect_transfer 模块的批量计算
"""

from typing import Any, Dict, List, Tuple
import numpy as np

from infra.features_v2.extractors.base import BaseExtractor, register
from infra.oect_transfer import BatchTransfer
from infra.logger_config import get_module_logger

logger = get_module_logger()


def _convert_to_3d_array(transfer_list: List[Dict]) -> np.ndarray:
    """将列表格式转换为 3D 数组

    Args:
        transfer_list: [{' Vg': array, 'Id': array}, ...]

    Returns:
        3D 数组 (n_steps, 2, max_points)
    """
    n_steps = len(transfer_list)
    max_points = max(len(step['Vg']) for step in transfer_list)

    # 预分配数组（用 NaN 填充）
    array_3d = np.full((n_steps, 2, max_points), np.nan, dtype=np.float32)

    for i, step_data in enumerate(transfer_list):
        n_points = len(step_data['Vg'])
        array_3d[i, 0, :n_points] = step_data['Vg']
        array_3d[i, 1, :n_points] = step_data['Id']

    return array_3d


@register('transfer.gm_max')
class GmMaxExtractor(BaseExtractor):
    """提取最大跨导绝对值

    参数：
        direction: 'forward', 'reverse', 或 'both'（默认）
        device_type: 'N' 或 'P'（默认 'N'）
    """

    def extract(self, data: Any, params: Dict[str, Any]) -> np.ndarray:
        transfer_list = data['transfer'] if isinstance(data, dict) else data

        # 转换为 3D 数组
        transfer_3d = _convert_to_3d_array(transfer_list)

        # 使用 BatchTransfer 计算
        device_type = params.get('device_type', 'N')
        batch_transfer = BatchTransfer(transfer_3d, device_type=device_type)

        # 根据方向选择输出
        direction = params.get('direction', 'forward')

        if direction == 'forward':
            return batch_transfer.absgm_max.forward
        elif direction == 'reverse':
            return batch_transfer.absgm_max.reverse
        elif direction == 'both':
            # 返回 (n_steps, 2)
            return np.column_stack([
                batch_transfer.absgm_max.forward,
                batch_transfer.absgm_max.reverse
            ])
        else:
            raise ValueError(f"无效的 direction: {direction}")

    @property
    def output_shape(self) -> Tuple:
        direction = self.params.get('direction', 'forward')
        if direction == 'both':
            return ('n_steps', 2)
        return ('n_steps',)


@register('transfer.Von')
class VonExtractor(BaseExtractor):
    """提取开启电压 (Von)

    参数：
        direction: 'forward', 'reverse', 或 'both'
        device_type: 'N' 或 'P'
    """

    def extract(self, data: Any, params: Dict[str, Any]) -> np.ndarray:
        transfer_list = data['transfer'] if isinstance(data, dict) else data
        transfer_3d = _convert_to_3d_array(transfer_list)

        device_type = params.get('device_type', 'N')
        batch_transfer = BatchTransfer(transfer_3d, device_type=device_type)

        direction = params.get('direction', 'forward')

        if direction == 'forward':
            return batch_transfer.Von.forward
        elif direction == 'reverse':
            return batch_transfer.Von.reverse
        elif direction == 'both':
            return np.column_stack([
                batch_transfer.Von.forward,
                batch_transfer.Von.reverse
            ])
        else:
            raise ValueError(f"无效的 direction: {direction}")

    @property
    def output_shape(self) -> Tuple:
        direction = self.params.get('direction', 'forward')
        if direction == 'both':
            return ('n_steps', 2)
        return ('n_steps',)


@register('transfer.absI_max')
class AbsIMaxExtractor(BaseExtractor):
    """提取最大电流绝对值

    参数：
        device_type: 'N' 或 'P'
    """

    def extract(self, data: Any, params: Dict[str, Any]) -> np.ndarray:
        transfer_list = data['transfer'] if isinstance(data, dict) else data
        transfer_3d = _convert_to_3d_array(transfer_list)

        device_type = params.get('device_type', 'N')
        batch_transfer = BatchTransfer(transfer_3d, device_type=device_type)

        return batch_transfer.absI_max.raw

    @property
    def output_shape(self) -> Tuple:
        return ('n_steps',)


@register('transfer.gm_max_coords')
class GmMaxCoordsExtractor(BaseExtractor):
    """提取最大跨导对应的坐标 (Vg, Id)

    参数：
        direction: 'forward' 或 'reverse'
        device_type: 'N' 或 'P'
        return_vg_only: 如果为 True，只返回 Vg（默认 False）
        return_id_only: 如果为 True，只返回 Id（默认 False）
    """

    def extract(self, data: Any, params: Dict[str, Any]) -> np.ndarray:
        transfer_list = data['transfer'] if isinstance(data, dict) else data
        transfer_3d = _convert_to_3d_array(transfer_list)

        device_type = params.get('device_type', 'N')
        batch_transfer = BatchTransfer(transfer_3d, device_type=device_type)

        direction = params.get('direction', 'forward')

        if direction == 'forward':
            coords = batch_transfer.absgm_max.forward_coords
        elif direction == 'reverse':
            coords = batch_transfer.absgm_max.reverse_coords
        else:
            raise ValueError(f"无效的 direction: {direction}")

        # coords 形状: (n_steps, 2)，第 0 列是 Vg，第 1 列是 Id
        if params.get('return_vg_only', False):
            return coords[:, 0]
        elif params.get('return_id_only', False):
            return coords[:, 1]
        else:
            return coords

    @property
    def output_shape(self) -> Tuple:
        if self.params.get('return_vg_only') or self.params.get('return_id_only'):
            return ('n_steps',)
        return ('n_steps', 2)


@register('transfer.Von_coords')
class VonCoordsExtractor(BaseExtractor):
    """提取 Von 对应的坐标 (Vg, Id)

    参数同 GmMaxCoordsExtractor
    """

    def extract(self, data: Any, params: Dict[str, Any]) -> np.ndarray:
        transfer_list = data['transfer'] if isinstance(data, dict) else data
        transfer_3d = _convert_to_3d_array(transfer_list)

        device_type = params.get('device_type', 'N')
        batch_transfer = BatchTransfer(transfer_3d, device_type=device_type)

        direction = params.get('direction', 'forward')

        if direction == 'forward':
            coords = batch_transfer.Von.forward_coords
        elif direction == 'reverse':
            coords = batch_transfer.Von.reverse_coords
        else:
            raise ValueError(f"无效的 direction: {direction}")

        if params.get('return_vg_only', False):
            return coords[:, 0]
        elif params.get('return_id_only', False):
            return coords[:, 1]
        else:
            return coords

    @property
    def output_shape(self) -> Tuple:
        if self.params.get('return_vg_only') or self.params.get('return_id_only'):
            return ('n_steps',)
        return ('n_steps', 2)


# 预注册所有 transfer 提取器（确保加载时注册）
__all__ = [
    'GmMaxExtractor',
    'VonExtractor',
    'AbsIMaxExtractor',
    'GmMaxCoordsExtractor',
    'VonCoordsExtractor',
]
