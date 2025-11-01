# batch_transfer.py
"""Batch transfer characteristic analysis for 3D numpy arrays"""

from dataclasses import dataclass
from numpy.typing import NDArray
import numpy as np
from typing import Optional, Dict, Any


@dataclass
class BatchSequence:
    """Batch version of Sequence - 2D arrays for each direction"""
    raw: NDArray[np.float64]      # Shape: [steps, data_points]
    forward: NDArray[np.float64]  # Shape: [steps, forward_points]
    reverse: NDArray[np.float64]  # Shape: [steps, reverse_points]


@dataclass  
class BatchPoint:
    """Batch version of Point - 1D arrays for each direction"""
    raw: NDArray[np.float64]      # Shape: [steps] - values only
    forward: NDArray[np.float64]  # Shape: [steps] - values only
    reverse: NDArray[np.float64]  # Shape: [steps] - values only
    
    # Coordinate information stored separately
    raw_coords: NDArray[np.float64]      # Shape: [steps, 2] - (Vg, Id) coordinates
    forward_coords: NDArray[np.float64]  # Shape: [steps, 2] - (Vg, Id) coordinates  
    reverse_coords: NDArray[np.float64]  # Shape: [steps, 2] - (Vg, Id) coordinates


class BatchTransfer:
    """Batch transfer characteristic analysis for 3D numpy arrays
    
    Handles 3D arrays with shape [step_idx, data_type, data_point_idx]
    where data_type dimension: 0=Vg (gate voltage), 1=Id (drain current)
    
    Provides the same interface as Transfer class but for batch processing:
    - Sequence properties become BatchSequence (2D arrays)
    - Point properties become BatchPoint (1D arrays with coordinates)
    """
    
    def __init__(self, data_3d: NDArray[np.float64], device_type: str = "N") -> None:
        """Initialize batch transfer analysis
        
        Args:
            data_3d: 3D numpy array with shape [steps, data_types, data_points]
                    data_types dimension: 0=Vg, 1=Id
            device_type: Device type ("N" or "P")
        """
        self.data_3d = np.asarray(data_3d, dtype=np.float64)
        self.device_type = device_type.upper()
        
        # Validate input array
        if self.data_3d.ndim != 3:
            raise ValueError("Input must be a 3D array with shape [steps, data_types, data_points]")
        
        if self.data_3d.shape[1] != 2:
            raise ValueError("Second dimension must have size 2 (Vg and Id)")
        
        self.step_count = self.data_3d.shape[0]
        self.data_point_count = self.data_3d.shape[2]
        
        if self.step_count == 0 or self.data_point_count == 0:
            raise ValueError("Array must contain at least one step and one data point")
        
        # Check for invalid data
        if np.any(np.isnan(self.data_3d)) or np.any(np.isinf(self.data_3d)):
            raise ValueError("Input array contains NaN or infinite values")
        
        # Compute turning point indices for all steps (中点作为转折点)
        self.tp_idx = (self.data_point_count - 1) // 2
        
        # Initialize all transfer characteristics
        self.Vg = self._compute_vg_sequences()
        self.I = self._compute_i_sequences()
        self.gm = self._compute_gm_sequences()
        
        # Point characteristics
        self.absgm_max = self._compute_absgm_max()
        self.gm_max = self._compute_gm_max()
        self.gm_min = self._compute_gm_min()
        self.absI_max = self._compute_absI_max()
        self.I_max = self._compute_I_max()
        self.absI_min = self._compute_absI_min()
        self.I_min = self._compute_I_min()
        self.Von = self._compute_Von()
    
    def _compute_vg_sequences(self) -> BatchSequence:
        """Compute gate voltage sequences for all steps"""
        # Raw: all data points [steps, data_points]
        raw = self.data_3d[:, 0, :]
        
        # Forward: data points up to turning point [steps, forward_points]
        forward = self.data_3d[:, 0, :self.tp_idx + 1]
        
        # Reverse: data points after turning point [steps, reverse_points] 
        reverse = self.data_3d[:, 0, self.tp_idx + 1:]
        
        return BatchSequence(raw=raw, forward=forward, reverse=reverse)
    
    def _compute_i_sequences(self) -> BatchSequence:
        """Compute drain current sequences for all steps"""
        # Raw: all data points [steps, data_points]
        raw = self.data_3d[:, 1, :]
        
        # Forward: data points up to turning point [steps, forward_points]
        forward = self.data_3d[:, 1, :self.tp_idx + 1]
        
        # Reverse: data points after turning point [steps, reverse_points]
        reverse = self.data_3d[:, 1, self.tp_idx + 1:]
        
        return BatchSequence(raw=raw, forward=forward, reverse=reverse)
    
    def _compute_gm_sequences(self) -> BatchSequence:
        """Compute transconductance (gm) sequences for all steps"""
        # Compute gm for each direction using vectorized operations
        raw_gm = np.zeros_like(self.I.raw)
        forward_gm = np.zeros_like(self.I.forward)
        reverse_gm = np.zeros_like(self.I.reverse)
        
        # Compute gm for each step
        for step_idx in range(self.step_count):
            raw_gm[step_idx, :] = self._safe_diff_1d(self.I.raw[step_idx, :], self.Vg.raw[step_idx, :])
            forward_gm[step_idx, :] = self._safe_diff_1d(self.I.forward[step_idx, :], self.Vg.forward[step_idx, :])  
            reverse_gm[step_idx, :] = self._safe_diff_1d(self.I.reverse[step_idx, :], self.Vg.reverse[step_idx, :])
        
        return BatchSequence(raw=raw_gm, forward=forward_gm, reverse=reverse_gm)
    
    def _compute_absgm_max(self) -> BatchPoint:
        """Compute maximum absolute transconductance for all steps"""
        steps = self.step_count
        
        # Initialize arrays
        raw_values = np.zeros(steps, dtype=np.float64)
        forward_values = np.zeros(steps, dtype=np.float64)
        reverse_values = np.zeros(steps, dtype=np.float64)
        
        raw_coords = np.zeros((steps, 2), dtype=np.float64)
        forward_coords = np.zeros((steps, 2), dtype=np.float64)
        reverse_coords = np.zeros((steps, 2), dtype=np.float64)
        
        for step_idx in range(steps):
            # Raw
            if self.gm.raw.shape[1] > 0:
                abs_gm = np.abs(self.gm.raw[step_idx, :])
                max_idx = abs_gm.argmax()
                raw_values[step_idx] = abs_gm[max_idx]
                raw_coords[step_idx, 0] = self.Vg.raw[step_idx, max_idx]  # Vg
                raw_coords[step_idx, 1] = self.I.raw[step_idx, max_idx]   # Id
            
            # Forward  
            if self.gm.forward.shape[1] > 0:
                abs_gm_fwd = np.abs(self.gm.forward[step_idx, :])
                max_idx_fwd = abs_gm_fwd.argmax()
                forward_values[step_idx] = abs_gm_fwd[max_idx_fwd]
                forward_coords[step_idx, 0] = self.Vg.forward[step_idx, max_idx_fwd]
                forward_coords[step_idx, 1] = self.I.forward[step_idx, max_idx_fwd]
            
            # Reverse
            if self.gm.reverse.shape[1] > 0:
                abs_gm_rev = np.abs(self.gm.reverse[step_idx, :])
                max_idx_rev = abs_gm_rev.argmax()  
                reverse_values[step_idx] = abs_gm_rev[max_idx_rev]
                reverse_coords[step_idx, 0] = self.Vg.reverse[step_idx, max_idx_rev]
                reverse_coords[step_idx, 1] = self.I.reverse[step_idx, max_idx_rev]
        
        return BatchPoint(
            raw=raw_values, forward=forward_values, reverse=reverse_values,
            raw_coords=raw_coords, forward_coords=forward_coords, reverse_coords=reverse_coords
        )
    
    def _compute_gm_max(self) -> BatchPoint:
        """Compute maximum transconductance for all steps"""
        steps = self.step_count
        
        raw_values = np.zeros(steps, dtype=np.float64)
        forward_values = np.zeros(steps, dtype=np.float64)
        reverse_values = np.zeros(steps, dtype=np.float64)
        
        raw_coords = np.zeros((steps, 2), dtype=np.float64)
        forward_coords = np.zeros((steps, 2), dtype=np.float64)
        reverse_coords = np.zeros((steps, 2), dtype=np.float64)
        
        for step_idx in range(steps):
            # Raw
            if self.gm.raw.shape[1] > 0:
                max_idx = self.gm.raw[step_idx, :].argmax()
                raw_values[step_idx] = self.gm.raw[step_idx, max_idx]
                raw_coords[step_idx, 0] = self.Vg.raw[step_idx, max_idx]
                raw_coords[step_idx, 1] = self.I.raw[step_idx, max_idx]
            
            # Forward
            if self.gm.forward.shape[1] > 0:
                max_idx_fwd = self.gm.forward[step_idx, :].argmax()
                forward_values[step_idx] = self.gm.forward[step_idx, max_idx_fwd]
                forward_coords[step_idx, 0] = self.Vg.forward[step_idx, max_idx_fwd]
                forward_coords[step_idx, 1] = self.I.forward[step_idx, max_idx_fwd]
            
            # Reverse
            if self.gm.reverse.shape[1] > 0:
                max_idx_rev = self.gm.reverse[step_idx, :].argmax()
                reverse_values[step_idx] = self.gm.reverse[step_idx, max_idx_rev]
                reverse_coords[step_idx, 0] = self.Vg.reverse[step_idx, max_idx_rev]
                reverse_coords[step_idx, 1] = self.I.reverse[step_idx, max_idx_rev]
        
        return BatchPoint(
            raw=raw_values, forward=forward_values, reverse=reverse_values,
            raw_coords=raw_coords, forward_coords=forward_coords, reverse_coords=reverse_coords
        )
    
    def _compute_gm_min(self) -> BatchPoint:
        """Compute minimum transconductance for all steps"""
        steps = self.step_count
        
        raw_values = np.zeros(steps, dtype=np.float64)
        forward_values = np.zeros(steps, dtype=np.float64)
        reverse_values = np.zeros(steps, dtype=np.float64)
        
        raw_coords = np.zeros((steps, 2), dtype=np.float64)
        forward_coords = np.zeros((steps, 2), dtype=np.float64)
        reverse_coords = np.zeros((steps, 2), dtype=np.float64)
        
        for step_idx in range(steps):
            # Raw
            if self.gm.raw.shape[1] > 0:
                min_idx = self.gm.raw[step_idx, :].argmin()
                raw_values[step_idx] = self.gm.raw[step_idx, min_idx]
                raw_coords[step_idx, 0] = self.Vg.raw[step_idx, min_idx]
                raw_coords[step_idx, 1] = self.I.raw[step_idx, min_idx]
            
            # Forward
            if self.gm.forward.shape[1] > 0:
                min_idx_fwd = self.gm.forward[step_idx, :].argmin()
                forward_values[step_idx] = self.gm.forward[step_idx, min_idx_fwd]
                forward_coords[step_idx, 0] = self.Vg.forward[step_idx, min_idx_fwd]
                forward_coords[step_idx, 1] = self.I.forward[step_idx, min_idx_fwd]
            
            # Reverse
            if self.gm.reverse.shape[1] > 0:
                min_idx_rev = self.gm.reverse[step_idx, :].argmin()
                reverse_values[step_idx] = self.gm.reverse[step_idx, min_idx_rev]
                reverse_coords[step_idx, 0] = self.Vg.reverse[step_idx, min_idx_rev]
                reverse_coords[step_idx, 1] = self.I.reverse[step_idx, min_idx_rev]
        
        return BatchPoint(
            raw=raw_values, forward=forward_values, reverse=reverse_values,
            raw_coords=raw_coords, forward_coords=forward_coords, reverse_coords=reverse_coords
        )
    
    def _compute_absI_max(self) -> BatchPoint:
        """Compute maximum absolute current for all steps"""
        steps = self.step_count
        
        raw_values = np.zeros(steps, dtype=np.float64)
        forward_values = np.zeros(steps, dtype=np.float64)
        reverse_values = np.zeros(steps, dtype=np.float64)
        
        raw_coords = np.zeros((steps, 2), dtype=np.float64)
        forward_coords = np.zeros((steps, 2), dtype=np.float64)
        reverse_coords = np.zeros((steps, 2), dtype=np.float64)
        
        for step_idx in range(steps):
            # Raw
            abs_i = np.abs(self.I.raw[step_idx, :])
            max_idx = abs_i.argmax()
            raw_values[step_idx] = abs_i[max_idx]
            raw_coords[step_idx, 0] = self.Vg.raw[step_idx, max_idx]
            raw_coords[step_idx, 1] = self.I.raw[step_idx, max_idx]
            
            # Forward
            if self.I.forward.shape[1] > 0:
                abs_i_fwd = np.abs(self.I.forward[step_idx, :])
                max_idx_fwd = abs_i_fwd.argmax()
                forward_values[step_idx] = abs_i_fwd[max_idx_fwd]
                forward_coords[step_idx, 0] = self.Vg.forward[step_idx, max_idx_fwd]
                forward_coords[step_idx, 1] = self.I.forward[step_idx, max_idx_fwd]
            
            # Reverse
            if self.I.reverse.shape[1] > 0:
                abs_i_rev = np.abs(self.I.reverse[step_idx, :])
                max_idx_rev = abs_i_rev.argmax()
                reverse_values[step_idx] = abs_i_rev[max_idx_rev]
                reverse_coords[step_idx, 0] = self.Vg.reverse[step_idx, max_idx_rev]
                reverse_coords[step_idx, 1] = self.I.reverse[step_idx, max_idx_rev]
        
        return BatchPoint(
            raw=raw_values, forward=forward_values, reverse=reverse_values,
            raw_coords=raw_coords, forward_coords=forward_coords, reverse_coords=reverse_coords
        )
    
    def _compute_I_max(self) -> BatchPoint:
        """Compute maximum current for all steps"""
        steps = self.step_count
        
        raw_values = np.zeros(steps, dtype=np.float64)
        forward_values = np.zeros(steps, dtype=np.float64)
        reverse_values = np.zeros(steps, dtype=np.float64)
        
        raw_coords = np.zeros((steps, 2), dtype=np.float64)
        forward_coords = np.zeros((steps, 2), dtype=np.float64)
        reverse_coords = np.zeros((steps, 2), dtype=np.float64)
        
        for step_idx in range(steps):
            # Raw
            max_idx = self.I.raw[step_idx, :].argmax()
            raw_values[step_idx] = self.I.raw[step_idx, max_idx]
            raw_coords[step_idx, 0] = self.Vg.raw[step_idx, max_idx]
            raw_coords[step_idx, 1] = self.I.raw[step_idx, max_idx]
            
            # Forward
            if self.I.forward.shape[1] > 0:
                max_idx_fwd = self.I.forward[step_idx, :].argmax()
                forward_values[step_idx] = self.I.forward[step_idx, max_idx_fwd]
                forward_coords[step_idx, 0] = self.Vg.forward[step_idx, max_idx_fwd]
                forward_coords[step_idx, 1] = self.I.forward[step_idx, max_idx_fwd]
            
            # Reverse
            if self.I.reverse.shape[1] > 0:
                max_idx_rev = self.I.reverse[step_idx, :].argmax()
                reverse_values[step_idx] = self.I.reverse[step_idx, max_idx_rev]
                reverse_coords[step_idx, 0] = self.Vg.reverse[step_idx, max_idx_rev]
                reverse_coords[step_idx, 1] = self.I.reverse[step_idx, max_idx_rev]
        
        return BatchPoint(
            raw=raw_values, forward=forward_values, reverse=reverse_values,
            raw_coords=raw_coords, forward_coords=forward_coords, reverse_coords=reverse_coords
        )
    
    def _compute_absI_min(self) -> BatchPoint:
        """Compute minimum absolute current for all steps"""
        steps = self.step_count
        
        raw_values = np.zeros(steps, dtype=np.float64)
        forward_values = np.zeros(steps, dtype=np.float64)
        reverse_values = np.zeros(steps, dtype=np.float64)
        
        raw_coords = np.zeros((steps, 2), dtype=np.float64)
        forward_coords = np.zeros((steps, 2), dtype=np.float64)
        reverse_coords = np.zeros((steps, 2), dtype=np.float64)
        
        for step_idx in range(steps):
            # Raw
            abs_i = np.abs(self.I.raw[step_idx, :])
            min_idx = abs_i.argmin()
            raw_values[step_idx] = abs_i[min_idx]
            raw_coords[step_idx, 0] = self.Vg.raw[step_idx, min_idx]
            raw_coords[step_idx, 1] = self.I.raw[step_idx, min_idx]
            
            # Forward
            if self.I.forward.shape[1] > 0:
                abs_i_fwd = np.abs(self.I.forward[step_idx, :])
                min_idx_fwd = abs_i_fwd.argmin()
                forward_values[step_idx] = abs_i_fwd[min_idx_fwd]
                forward_coords[step_idx, 0] = self.Vg.forward[step_idx, min_idx_fwd]
                forward_coords[step_idx, 1] = self.I.forward[step_idx, min_idx_fwd]
            
            # Reverse
            if self.I.reverse.shape[1] > 0:
                abs_i_rev = np.abs(self.I.reverse[step_idx, :])
                min_idx_rev = abs_i_rev.argmin()
                reverse_values[step_idx] = abs_i_rev[min_idx_rev]
                reverse_coords[step_idx, 0] = self.Vg.reverse[step_idx, min_idx_rev]
                reverse_coords[step_idx, 1] = self.I.reverse[step_idx, min_idx_rev]
        
        return BatchPoint(
            raw=raw_values, forward=forward_values, reverse=reverse_values,
            raw_coords=raw_coords, forward_coords=forward_coords, reverse_coords=reverse_coords
        )
    
    def _compute_I_min(self) -> BatchPoint:
        """Compute minimum current for all steps"""
        steps = self.step_count
        
        raw_values = np.zeros(steps, dtype=np.float64)
        forward_values = np.zeros(steps, dtype=np.float64)
        reverse_values = np.zeros(steps, dtype=np.float64)
        
        raw_coords = np.zeros((steps, 2), dtype=np.float64)
        forward_coords = np.zeros((steps, 2), dtype=np.float64)
        reverse_coords = np.zeros((steps, 2), dtype=np.float64)
        
        for step_idx in range(steps):
            # Raw
            min_idx = self.I.raw[step_idx, :].argmin()
            raw_values[step_idx] = self.I.raw[step_idx, min_idx]
            raw_coords[step_idx, 0] = self.Vg.raw[step_idx, min_idx]
            raw_coords[step_idx, 1] = self.I.raw[step_idx, min_idx]
            
            # Forward
            if self.I.forward.shape[1] > 0:
                min_idx_fwd = self.I.forward[step_idx, :].argmin()
                forward_values[step_idx] = self.I.forward[step_idx, min_idx_fwd]
                forward_coords[step_idx, 0] = self.Vg.forward[step_idx, min_idx_fwd]
                forward_coords[step_idx, 1] = self.I.forward[step_idx, min_idx_fwd]
            
            # Reverse
            if self.I.reverse.shape[1] > 0:
                min_idx_rev = self.I.reverse[step_idx, :].argmin()
                reverse_values[step_idx] = self.I.reverse[step_idx, min_idx_rev]
                reverse_coords[step_idx, 0] = self.Vg.reverse[step_idx, min_idx_rev]
                reverse_coords[step_idx, 1] = self.I.reverse[step_idx, min_idx_rev]
        
        return BatchPoint(
            raw=raw_values, forward=forward_values, reverse=reverse_values,
            raw_coords=raw_coords, forward_coords=forward_coords, reverse_coords=reverse_coords
        )
    
    def _compute_Von(self) -> BatchPoint:
        """Compute threshold voltage (Von) for all steps"""
        steps = self.step_count
        
        raw_values = np.zeros(steps, dtype=np.float64)
        forward_values = np.zeros(steps, dtype=np.float64)
        reverse_values = np.zeros(steps, dtype=np.float64)
        
        raw_coords = np.zeros((steps, 2), dtype=np.float64)
        forward_coords = np.zeros((steps, 2), dtype=np.float64)
        reverse_coords = np.zeros((steps, 2), dtype=np.float64)
        
        for step_idx in range(steps):
            try:
                # Raw
                if self.I.raw.shape[1] > 0 and self.Vg.raw.shape[1] > 0:
                    log_Id = np.log10(np.clip(np.abs(self.I.raw[step_idx, :]), 1e-12, None))
                    dlogId_dVg = self._safe_diff_1d(log_Id, self.Vg.raw[step_idx, :])
                    
                    if len(dlogId_dVg) > 0:
                        if self.device_type == "N":
                            von_idx = dlogId_dVg.argmax()  # N-type: maximum slope
                        else:
                            von_idx = dlogId_dVg.argmin()  # P-type: minimum slope
                        
                        raw_values[step_idx] = self.Vg.raw[step_idx, von_idx]
                        raw_coords[step_idx, 0] = self.Vg.raw[step_idx, von_idx]
                        raw_coords[step_idx, 1] = self.I.raw[step_idx, von_idx]
                
                # Forward
                if self.I.forward.shape[1] > 0 and self.Vg.forward.shape[1] > 0:
                    log_Id_fwd = np.log10(np.clip(np.abs(self.I.forward[step_idx, :]), 1e-12, None))
                    dlogId_dVg_fwd = self._safe_diff_1d(log_Id_fwd, self.Vg.forward[step_idx, :])
                    
                    if len(dlogId_dVg_fwd) > 0:
                        if self.device_type == "N":
                            von_idx_fwd = dlogId_dVg_fwd.argmax()
                        else:
                            von_idx_fwd = dlogId_dVg_fwd.argmin()
                        
                        forward_values[step_idx] = self.Vg.forward[step_idx, von_idx_fwd]
                        forward_coords[step_idx, 0] = self.Vg.forward[step_idx, von_idx_fwd]
                        forward_coords[step_idx, 1] = self.I.forward[step_idx, von_idx_fwd]
                
                # Reverse
                if self.I.reverse.shape[1] > 0 and self.Vg.reverse.shape[1] > 0:
                    log_Id_rev = np.log10(np.clip(np.abs(self.I.reverse[step_idx, :]), 1e-12, None))
                    dlogId_dVg_rev = self._safe_diff_1d(log_Id_rev, self.Vg.reverse[step_idx, :])
                    
                    if len(dlogId_dVg_rev) > 0:
                        if self.device_type == "N":
                            von_idx_rev = dlogId_dVg_rev.argmax()
                        else:
                            von_idx_rev = dlogId_dVg_rev.argmin()
                        
                        reverse_values[step_idx] = self.Vg.reverse[step_idx, von_idx_rev]
                        reverse_coords[step_idx, 0] = self.Vg.reverse[step_idx, von_idx_rev]
                        reverse_coords[step_idx, 1] = self.I.reverse[step_idx, von_idx_rev]
                        
            except Exception:
                # If calculation fails for this step, leave as zero
                continue
        
        return BatchPoint(
            raw=raw_values, forward=forward_values, reverse=reverse_values,
            raw_coords=raw_coords, forward_coords=forward_coords, reverse_coords=reverse_coords
        )
    
    @staticmethod
    def _safe_diff_1d(f: NDArray[np.float64], x: NDArray[np.float64]) -> NDArray[np.float64]:
        """Safe differentiation for 1D arrays"""
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
    
    def get_data_summary(self) -> Dict[str, Any]:
        """Get summary information about the batch data"""
        return {
            'shape': self.data_3d.shape,
            'step_count': self.step_count,
            'data_point_count': self.data_point_count,
            'device_type': self.device_type,
            'turning_point_idx': self.tp_idx,
            'total_data_points': self.data_3d.size,
            'memory_size_mb': self.data_3d.nbytes / (1024 * 1024),
            'vg_global_range': (float(self.data_3d[:, 0, :].min()), 
                               float(self.data_3d[:, 0, :].max())),
            'id_global_range': (float(self.data_3d[:, 1, :].min()), 
                               float(self.data_3d[:, 1, :].max())),
        }


def create_batch_transfer_from_experiment_data(transfer_data_3d: NDArray[np.float64], 
                                             device_type: str = "N") -> BatchTransfer:
    """Convenience function to create BatchTransfer from experiment batch data
    
    Args:
        transfer_data_3d: 3D array from experiment.get_transfer_all_measurement()
        device_type: Device type ("N" or "P")
    
    Returns:
        BatchTransfer instance ready for analysis
    """
    return BatchTransfer(transfer_data_3d, device_type)


def analyze_experiment_transfer_batch(experiment_path: str, device_type: str = "N") -> Optional[BatchTransfer]:
    """Analyze transfer data from an experiment file using batch processing
    
    Args:
        experiment_path: Path to HDF5 experiment file
        device_type: Device type ("N" or "P")
        
    Returns:
        BatchTransfer instance or None if no transfer data found
    """
    try:
        from experiment import Experiment
        
        exp = Experiment(experiment_path)
        transfer_data = exp.get_transfer_all_measurement()
        
        if transfer_data is not None and 'measurement_data' in transfer_data:
            measurement_3d = transfer_data['measurement_data']
            return BatchTransfer(measurement_3d, device_type)
        else:
            print(f"No transfer data found in {experiment_path}")
            return None
            
    except Exception as e:
        print(f"Error loading experiment data: {e}")
        return None