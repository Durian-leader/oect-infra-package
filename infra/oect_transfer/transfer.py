# transfer.py
from dataclasses import dataclass
from numpy.typing import NDArray
import numpy as np
from typing import List, Optional, Tuple, Union


@dataclass
class Sequence:
    raw: NDArray[np.float64]
    forward: NDArray[np.float64]
    reverse: NDArray[np.float64]


@dataclass
class Point:
    raw: Union[float, Tuple[float, Tuple[float, float]]]
    forward: Union[float, Tuple[float, Tuple[float, float]]]
    reverse: Union[float, Tuple[float, Tuple[float, float]]]


class Transfer:
    def __init__(
        self, x: NDArray[np.float64], y: NDArray[np.float64], device_type: str = "N"
    ) -> None:
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        # Validate input arrays
        if x.ndim != 1 or y.ndim != 1:
            raise ValueError("x and y must be 1D arrays.")
        if x.shape[0] != y.shape[0]:
            print(x.shape[0], y.shape[0])
            print(x, y)
            raise ValueError("x and y must have the same length.")
        if x.size == 0 or y.size == 0:
            raise ValueError("x and y must not be empty.")
        if np.any(np.isnan(x)) or np.any(np.isnan(y)):
            raise ValueError("x and y must not contain NaN values.")
        if np.any(np.isinf(x)) or np.any(np.isinf(y)):
            raise ValueError("x and y must not contain infinite values.")

        # 修复转折点查找逻辑，添加错误处理
        self.tp_idx = (len(x)-1) // 2

        # Avoid double-counting the turning point in reverse to prevent spurious gm spikes
        self.Vg = Sequence(raw=x, forward=x[: self.tp_idx + 1], reverse=x[self.tp_idx + 1:])
        self.I = Sequence(raw=y, forward=y[: self.tp_idx + 1], reverse=y[self.tp_idx + 1:])

        self.gm = self._compute_gm()
        self.absgm_max = self._compute_absgm_max()
        self.gm_max = self._compute_gm_max()
        self.gm_min = self._compute_gm_min()
        self.absI_max = self._compute_absI_max()
        self.I_max = self._compute_I_max()
        self.absI_min = self._compute_absI_min()
        self.I_min = self._compute_I_min()
        self.Von = self._compute_Von(device_type=device_type)

    def _compute_gm(self) -> Sequence:
        """
        计算跨导 gm = dy/dx，用 safe_diff 方法处理
        :return: Sequence 包含 raw / forward / reverse 的 gm
        """
        return Sequence(
            raw=self.safe_diff(self.I.raw, self.Vg.raw),
            forward=self.safe_diff(self.I.forward, self.Vg.forward),
            reverse=self.safe_diff(self.I.reverse, self.Vg.reverse),
        )

    def _compute_absgm_max(self) -> Point:
        """
        计算gm的绝对值的最大点
        :return: Point 包含 raw / forward / reverse 的 absgm_max，格式为(值, (Vg, Id))
        """
        if len(self.gm.raw) == 0:
            return Point(raw=(0.0, (0.0, 0.0)), forward=(0.0, (0.0, 0.0)), reverse=(0.0, (0.0, 0.0)))
            
        # Raw数据处理
        absgm_max_index = np.abs(self.gm.raw).argmax()
        absgm_max_value = float(np.abs(self.gm.raw).max())
        # gm索引对应原始数据的中点索引
        raw_vg = float(self.Vg.raw[absgm_max_index]) if absgm_max_index < len(self.Vg.raw) else 0.0
        raw_id = float(self.I.raw[absgm_max_index]) if absgm_max_index < len(self.I.raw) else 0.0
        
        # Forward数据处理
        forward_result = (0.0, (0.0, 0.0))
        if len(self.gm.forward) > 0:
            forward_max_idx = np.abs(self.gm.forward).argmax()
            forward_max_value = float(np.abs(self.gm.forward).max())
            forward_vg = float(self.Vg.forward[forward_max_idx]) if forward_max_idx < len(self.Vg.forward) else 0.0
            forward_id = float(self.I.forward[forward_max_idx]) if forward_max_idx < len(self.I.forward) else 0.0
            forward_result = (forward_max_value, (forward_vg, forward_id))
        
        # Reverse数据处理
        reverse_result = (0.0, (0.0, 0.0))
        if len(self.gm.reverse) > 0:
            reverse_max_idx = np.abs(self.gm.reverse).argmax()
            reverse_max_value = float(np.abs(self.gm.reverse).max())
            reverse_vg = float(self.Vg.reverse[reverse_max_idx]) if reverse_max_idx < len(self.Vg.reverse) else 0.0
            reverse_id = float(self.I.reverse[reverse_max_idx]) if reverse_max_idx < len(self.I.reverse) else 0.0
            reverse_result = (reverse_max_value, (reverse_vg, reverse_id))
            
        return Point(
            raw=(absgm_max_value, (raw_vg, raw_id)),
            forward=forward_result,
            reverse=reverse_result
        )
    
    def _compute_gm_max(self) -> Point:
        """
        计算最大跨导点
        :return: Point 包含 raw / forward / reverse 的 gm_max，格式为(值, (Vg, Id))
        """
        if len(self.gm.raw) == 0:
            return Point(raw=(0.0, (0.0, 0.0)), forward=(0.0, (0.0, 0.0)), reverse=(0.0, (0.0, 0.0)))
            
        # Raw数据处理
        gm_max_index = self.gm.raw.argmax()
        gm_max_value = float(self.gm.raw.max())
        raw_vg = float(self.Vg.raw[gm_max_index]) if gm_max_index < len(self.Vg.raw) else 0.0
        raw_id = float(self.I.raw[gm_max_index]) if gm_max_index < len(self.I.raw) else 0.0
        
        # Forward数据处理
        forward_result = (0.0, (0.0, 0.0))
        if len(self.gm.forward) > 0:
            forward_max_idx = self.gm.forward.argmax()
            forward_max_value = float(self.gm.forward.max())
            forward_vg = float(self.Vg.forward[forward_max_idx]) if forward_max_idx < len(self.Vg.forward) else 0.0
            forward_id = float(self.I.forward[forward_max_idx]) if forward_max_idx < len(self.I.forward) else 0.0
            forward_result = (forward_max_value, (forward_vg, forward_id))
        
        # Reverse数据处理
        reverse_result = (0.0, (0.0, 0.0))
        if len(self.gm.reverse) > 0:
            reverse_max_idx = self.gm.reverse.argmax()
            reverse_max_value = float(self.gm.reverse.max())
            reverse_vg = float(self.Vg.reverse[reverse_max_idx]) if reverse_max_idx < len(self.Vg.reverse) else 0.0
            reverse_id = float(self.I.reverse[reverse_max_idx]) if reverse_max_idx < len(self.I.reverse) else 0.0
            reverse_result = (reverse_max_value, (reverse_vg, reverse_id))
            
        return Point(
            raw=(gm_max_value, (raw_vg, raw_id)),
            forward=forward_result,
            reverse=reverse_result
        )
    
    def _compute_gm_min(self) -> Point:
        """
        计算最小跨导点
        :return: Point 包含 raw / forward / reverse 的 gm_min，格式为(值, (Vg, Id))
        """
        if len(self.gm.raw) == 0:
            return Point(raw=(0.0, (0.0, 0.0)), forward=(0.0, (0.0, 0.0)), reverse=(0.0, (0.0, 0.0)))
            
        # Raw数据处理
        gm_min_index = self.gm.raw.argmin()
        gm_min_value = float(self.gm.raw.min())
        raw_vg = float(self.Vg.raw[gm_min_index]) if gm_min_index < len(self.Vg.raw) else 0.0
        raw_id = float(self.I.raw[gm_min_index]) if gm_min_index < len(self.I.raw) else 0.0
        
        # Forward数据处理
        forward_result = (0.0, (0.0, 0.0))
        if len(self.gm.forward) > 0:
            forward_min_idx = self.gm.forward.argmin()
            forward_min_value = float(self.gm.forward.min())
            forward_vg = float(self.Vg.forward[forward_min_idx]) if forward_min_idx < len(self.Vg.forward) else 0.0
            forward_id = float(self.I.forward[forward_min_idx]) if forward_min_idx < len(self.I.forward) else 0.0
            forward_result = (forward_min_value, (forward_vg, forward_id))
        
        # Reverse数据处理
        reverse_result = (0.0, (0.0, 0.0))
        if len(self.gm.reverse) > 0:
            reverse_min_idx = self.gm.reverse.argmin()
            reverse_min_value = float(self.gm.reverse.min())
            reverse_vg = float(self.Vg.reverse[reverse_min_idx]) if reverse_min_idx < len(self.Vg.reverse) else 0.0
            reverse_id = float(self.I.reverse[reverse_min_idx]) if reverse_min_idx < len(self.I.reverse) else 0.0
            reverse_result = (reverse_min_value, (reverse_vg, reverse_id))
            
        return Point(
            raw=(gm_min_value, (raw_vg, raw_id)),
            forward=forward_result,
            reverse=reverse_result
        )

    def _compute_absI_max(self) -> Point:
        """
        计算电流绝对值的最大点 absI_max
        :return: Point 包含 raw / forward / reverse 的 absI_max，格式为(值, (Vg, Id))
        """
        if len(self.I.raw) == 0:
            return Point(raw=(0.0, (0.0, 0.0)), forward=(0.0, (0.0, 0.0)), reverse=(0.0, (0.0, 0.0)))
            
        # Raw数据处理
        absI_max_index = np.abs(self.I.raw).argmax()
        absI_max_value = float(np.abs(self.I.raw).max())
        raw_vg = float(self.Vg.raw[absI_max_index]) if absI_max_index < len(self.Vg.raw) else 0.0
        raw_id = float(self.I.raw[absI_max_index]) if absI_max_index < len(self.I.raw) else 0.0
        
        # Forward数据处理
        forward_result = (0.0, (0.0, 0.0))
        if len(self.I.forward) > 0:
            forward_max_idx = np.abs(self.I.forward).argmax()
            forward_max_value = float(np.abs(self.I.forward).max())
            forward_vg = float(self.Vg.forward[forward_max_idx]) if forward_max_idx < len(self.Vg.forward) else 0.0
            forward_id = float(self.I.forward[forward_max_idx]) if forward_max_idx < len(self.I.forward) else 0.0
            forward_result = (forward_max_value, (forward_vg, forward_id))
        
        # Reverse数据处理
        reverse_result = (0.0, (0.0, 0.0))
        if len(self.I.reverse) > 0:
            reverse_max_idx = np.abs(self.I.reverse).argmax()
            reverse_max_value = float(np.abs(self.I.reverse).max())
            reverse_vg = float(self.Vg.reverse[reverse_max_idx]) if reverse_max_idx < len(self.Vg.reverse) else 0.0
            reverse_id = float(self.I.reverse[reverse_max_idx]) if reverse_max_idx < len(self.I.reverse) else 0.0
            reverse_result = (reverse_max_value, (reverse_vg, reverse_id))
            
        return Point(
            raw=(absI_max_value, (raw_vg, raw_id)),
            forward=forward_result,
            reverse=reverse_result
        )
    
    def _compute_I_max(self) -> Point:
        """
        计算最大电流点
        :return: Point 包含 raw / forward / reverse 的 I_max，格式为(值, (Vg, Id))
        """
        if len(self.I.raw) == 0:
            return Point(raw=(0.0, (0.0, 0.0)), forward=(0.0, (0.0, 0.0)), reverse=(0.0, (0.0, 0.0)))
            
        # Raw数据处理
        I_max_index = self.I.raw.argmax()
        I_max_value = float(self.I.raw.max())
        raw_vg = float(self.Vg.raw[I_max_index]) if I_max_index < len(self.Vg.raw) else 0.0
        raw_id = float(self.I.raw[I_max_index]) if I_max_index < len(self.I.raw) else 0.0
        
        # Forward数据处理
        forward_result = (0.0, (0.0, 0.0))
        if len(self.I.forward) > 0:
            forward_max_idx = self.I.forward.argmax()
            forward_max_value = float(self.I.forward.max())
            forward_vg = float(self.Vg.forward[forward_max_idx]) if forward_max_idx < len(self.Vg.forward) else 0.0
            forward_id = float(self.I.forward[forward_max_idx]) if forward_max_idx < len(self.I.forward) else 0.0
            forward_result = (forward_max_value, (forward_vg, forward_id))
        
        # Reverse数据处理
        reverse_result = (0.0, (0.0, 0.0))
        if len(self.I.reverse) > 0:
            reverse_max_idx = self.I.reverse.argmax()
            reverse_max_value = float(self.I.reverse.max())
            reverse_vg = float(self.Vg.reverse[reverse_max_idx]) if reverse_max_idx < len(self.Vg.reverse) else 0.0
            reverse_id = float(self.I.reverse[reverse_max_idx]) if reverse_max_idx < len(self.I.reverse) else 0.0
            reverse_result = (reverse_max_value, (reverse_vg, reverse_id))
            
        return Point(
            raw=(I_max_value, (raw_vg, raw_id)),
            forward=forward_result,
            reverse=reverse_result
        )

    def _compute_absI_min(self) -> Point:
        """
        计算电流绝对值的最小点 absI_min
        :return: Point 包含 raw / forward / reverse 的 absI_min，格式为(值, (Vg, Id))
        """
        if len(self.I.raw) == 0:
            return Point(raw=(0.0, (0.0, 0.0)), forward=(0.0, (0.0, 0.0)), reverse=(0.0, (0.0, 0.0)))
            
        # Raw数据处理
        absI_min_index = np.abs(self.I.raw).argmin()
        absI_min_value = float(np.abs(self.I.raw).min())
        raw_vg = float(self.Vg.raw[absI_min_index]) if absI_min_index < len(self.Vg.raw) else 0.0
        raw_id = float(self.I.raw[absI_min_index]) if absI_min_index < len(self.I.raw) else 0.0
        
        # Forward数据处理
        forward_result = (0.0, (0.0, 0.0))
        if len(self.I.forward) > 0:
            forward_min_idx = np.abs(self.I.forward).argmin()
            forward_min_value = float(np.abs(self.I.forward).min())
            forward_vg = float(self.Vg.forward[forward_min_idx]) if forward_min_idx < len(self.Vg.forward) else 0.0
            forward_id = float(self.I.forward[forward_min_idx]) if forward_min_idx < len(self.I.forward) else 0.0
            forward_result = (forward_min_value, (forward_vg, forward_id))
        
        # Reverse数据处理
        reverse_result = (0.0, (0.0, 0.0))
        if len(self.I.reverse) > 0:
            reverse_min_idx = np.abs(self.I.reverse).argmin()
            reverse_min_value = float(np.abs(self.I.reverse).min())
            reverse_vg = float(self.Vg.reverse[reverse_min_idx]) if reverse_min_idx < len(self.Vg.reverse) else 0.0
            reverse_id = float(self.I.reverse[reverse_min_idx]) if reverse_min_idx < len(self.I.reverse) else 0.0
            reverse_result = (reverse_min_value, (reverse_vg, reverse_id))
            
        return Point(
            raw=(absI_min_value, (raw_vg, raw_id)),
            forward=forward_result,
            reverse=reverse_result
        )
    
    def _compute_I_min(self) -> Point:
        """
        计算最小电流点
        :return: Point 包含 raw / forward / reverse 的 I_min，格式为(值, (Vg, Id))
        """
        if len(self.I.raw) == 0:
            return Point(raw=(0.0, (0.0, 0.0)), forward=(0.0, (0.0, 0.0)), reverse=(0.0, (0.0, 0.0)))
            
        # Raw数据处理
        I_min_index = self.I.raw.argmin()
        I_min_value = float(self.I.raw.min())
        raw_vg = float(self.Vg.raw[I_min_index]) if I_min_index < len(self.Vg.raw) else 0.0
        raw_id = float(self.I.raw[I_min_index]) if I_min_index < len(self.I.raw) else 0.0
        
        # Forward数据处理
        forward_result = (0.0, (0.0, 0.0))
        if len(self.I.forward) > 0:
            forward_min_idx = self.I.forward.argmin()
            forward_min_value = float(self.I.forward.min())
            forward_vg = float(self.Vg.forward[forward_min_idx]) if forward_min_idx < len(self.Vg.forward) else 0.0
            forward_id = float(self.I.forward[forward_min_idx]) if forward_min_idx < len(self.I.forward) else 0.0
            forward_result = (forward_min_value, (forward_vg, forward_id))
        
        # Reverse数据处理
        reverse_result = (0.0, (0.0, 0.0))
        if len(self.I.reverse) > 0:
            reverse_min_idx = self.I.reverse.argmin()
            reverse_min_value = float(self.I.reverse.min())
            reverse_vg = float(self.Vg.reverse[reverse_min_idx]) if reverse_min_idx < len(self.Vg.reverse) else 0.0
            reverse_id = float(self.I.reverse[reverse_min_idx]) if reverse_min_idx < len(self.I.reverse) else 0.0
            reverse_result = (reverse_min_value, (reverse_vg, reverse_id))
            
        return Point(
            raw=(I_min_value, (raw_vg, raw_id)),
            forward=forward_result,
            reverse=reverse_result
        )
    
    def _compute_Von(self, device_type: str = "N") -> Point:
        """
        计算Von (阈值电压)
        对于N型器件，使用对数斜率最大法
        对于P型器件，使用对数斜率最小法

        :param device_type: 器件类型，"N"表示N型，"P"表示P型
        :return: Point 包含 raw / forward / reverse 的 Von 值，格式为(值, (Vg, Id))
        """
        try:
            if len(self.I.raw) == 0 or len(self.Vg.raw) == 0:
                return Point(raw=(0.0, (0.0, 0.0)), forward=(0.0, (0.0, 0.0)), reverse=(0.0, (0.0, 0.0)))
                
            # 计算raw的Von
            log_Id_raw = np.log10(np.clip(np.abs(self.I.raw), 1e-12, None))
            dlogId_dVg_raw = self.safe_diff(log_Id_raw, self.Vg.raw)

            if len(dlogId_dVg_raw) == 0:
                return Point(raw=(0.0, (0.0, 0.0)), forward=(0.0, (0.0, 0.0)), reverse=(0.0, (0.0, 0.0)))

            # 根据器件类型选择最大或最小斜率点
            if device_type.upper() == "N":
                idx_raw = dlogId_dVg_raw.argmax()  # N型选择最大斜率点
            else:  # 默认为P型
                idx_raw = dlogId_dVg_raw.argmin()  # P型选择最小斜率点

            Von_raw_value = float(self.Vg.raw[idx_raw]) if idx_raw < len(self.Vg.raw) else 0.0
            raw_vg = Von_raw_value
            raw_id = float(self.I.raw[idx_raw]) if idx_raw < len(self.I.raw) else 0.0

            # 计算forward的Von
            forward_result = (0.0, (0.0, 0.0))
            if len(self.I.forward) > 0 and len(self.Vg.forward) > 0:
                log_Id_forward = np.log10(np.clip(np.abs(self.I.forward), 1e-12, None))
                dlogId_dVg_forward = self.safe_diff(log_Id_forward, self.Vg.forward)

                if len(dlogId_dVg_forward) > 0:
                    if device_type.upper() == "N":
                        idx_forward = dlogId_dVg_forward.argmax()
                    else:
                        idx_forward = dlogId_dVg_forward.argmin()

                    Von_forward_value = float(self.Vg.forward[idx_forward]) if idx_forward < len(self.Vg.forward) else 0.0
                    forward_vg = Von_forward_value
                    forward_id = float(self.I.forward[idx_forward]) if idx_forward < len(self.I.forward) else 0.0
                    forward_result = (Von_forward_value, (forward_vg, forward_id))

            # 计算reverse的Von
            reverse_result = (0.0, (0.0, 0.0))
            if len(self.I.reverse) > 0 and len(self.Vg.reverse) > 0:
                log_Id_reverse = np.log10(np.clip(np.abs(self.I.reverse), 1e-12, None))
                dlogId_dVg_reverse = self.safe_diff(log_Id_reverse, self.Vg.reverse)

                if len(dlogId_dVg_reverse) > 0:
                    if device_type.upper() == "N":
                        idx_reverse = dlogId_dVg_reverse.argmax()
                    else:
                        idx_reverse = dlogId_dVg_reverse.argmin()

                    Von_reverse_value = float(self.Vg.reverse[idx_reverse]) if idx_reverse < len(self.Vg.reverse) else 0.0
                    reverse_vg = Von_reverse_value
                    reverse_id = float(self.I.reverse[idx_reverse]) if idx_reverse < len(self.I.reverse) else 0.0
                    reverse_result = (Von_reverse_value, (reverse_vg, reverse_id))

            return Point(
                raw=(Von_raw_value, (raw_vg, raw_id)),
                forward=forward_result,
                reverse=reverse_result
            )
        except Exception as e:
            print(f"警告：Von计算失败: {e}")
            return Point(raw=(0.0, (0.0, 0.0)), forward=(0.0, (0.0, 0.0)), reverse=(0.0, (0.0, 0.0)))

    @staticmethod
    def safe_diff(
        f: NDArray[np.float64], x: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        """
        计算稳定差分导数：前向 + 后向 + 中心差分组合，避免除以0或nan，转折点处做前向差分和后向差分的平均值
        支持任意长度数组
        """

        return numba_safe_diff(f, x)


import numba

@numba.jit(nopython=True) # 添加这个装饰器
def numba_safe_diff(f: NDArray[np.float64], x: NDArray[np.float64]) -> NDArray[np.float64]:
    # 这里使用你原来的 safe_diff 循环代码
    n = len(f)
    if n < 2:
        return np.zeros(n, dtype=np.float64)

    df = np.zeros(n, dtype=np.float64)

    for i in range(n):
        if i == 0:
            if n > 1:
                dx = x[1] - x[0]
                if abs(dx) < 1e-12:
                    dx = 1e-12
                df[i] = (f[1] - f[0]) / dx
        elif i == n - 1:
            dx = x[n-1] - x[n-2]
            if abs(dx) < 1e-12:
                dx = 1e-12
            df[i] = (f[n-1] - f[n-2]) / dx
        else:
            dx1 = x[i] - x[i - 1]
            dx2 = x[i + 1] - x[i]
            if abs(dx1) < 1e-12:
                dx1 = 1e-12
            if abs(dx2) < 1e-12:
                dx2 = 1e-12
            df1 = (f[i] - f[i - 1]) / dx1
            df2 = (f[i + 1] - f[i]) / dx2
            df[i] = (df1 + df2) / 2.0

    return df