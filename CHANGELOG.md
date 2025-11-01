# Changelog

All notable changes to the `oect-infra` package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.8] - 2025-11-01

### Fixed
- **V2 Lambda Functions**: Fixed lambda function parameter mismatches in feature configuration files
  - **Root Cause**: Configuration files used dictionary-style lambdas (`lambda inputs: inputs['key']`) but executor passes positional arguments
  - **Fixed Files**:
    - `catalog/feature_configs/v2_ml_ready.yaml` (3 locations):
      - Line 93: `gm_ratio` → `lambda gm_fwd, gm_rev: gm_fwd / gm_rev`
      - Line 101: `Von_diff` → `lambda von_fwd, von_rev: von_fwd - von_rev`
      - Line 111: `gm_max_forward_norm` (verified safe, single input)
    - `features_v2/config/templates/v2_mixed.yaml` (Line 79):
      - `gm_to_peak_ratio` → `lambda gm, peak: gm / peak`
    - `features_v2/config/templates/v2_transfer_basic.yaml` (Line 84):
      - `gm_ratio` → `lambda gm_fwd, gm_rev: gm_fwd / gm_rev`
  - **Error Resolved**: `<lambda>() takes 1 positional argument but 2 were given`
  - **Technical Details**: Executor calls multi-input lambdas as `func(*[val1, val2], **params)`, not `func({'key1': val1, 'key2': val2})`

### Impact
- V2 feature extraction now works correctly in all modes (single/batch, CLI/Python API)
- Multi-input derived features (ratios, differences) compute successfully
- Affects `process_data_pipeline()`, `batch_extract_features_v2()`, and `exp.extract_features_v2()`

## [1.0.7] - 2025-11-01

### Fixed
- **V1 Feature Extraction**: Fixed import error in `features_version/v1_feature.py` where `BatchTransfer` was incorrectly imported from external PyPI package instead of local `infra.oect_transfer` module
  - Changed `from oect_transfer import BatchTransfer` to `from ..oect_transfer import BatchTransfer`
  - This caused "cannot import name 'BatchTransfer'" errors during batch feature extraction

- **V2 Feature Extraction**: Fixed configuration path resolution in multiprocess wrapper `_extract_v2_wrapper` in `catalog/unified.py`
  - Added proper config file lookup logic to resolve config names (e.g., `'v2_ml_ready'`) to full paths
  - Now searches in `catalog/feature_configs/` and `features_v2/config/templates/` directories
  - This fixed "不支持的配置文件格式: " (empty string) errors in parallel V2 feature extraction

### Impact
- Users can now successfully run `process_data_pipeline()` with both V1 and V2 feature extraction enabled
- Multiprocess V2 feature extraction (`batch_extract_features_v2` with `n_workers > 1`) now works correctly

## [1.0.6] - 2025-01-11

### Added
- Initial PyPI release
- Complete OECT data processing infrastructure
- Unified experiment management with `UnifiedExperimentManager`
- Features V2 system with DAG-based computation
- Catalog integration with workflow metadata
- Stability report generation
- CLI tools for catalog and stability report operations

### Components
- `csv2hdf`: CSV/JSON to HDF5 conversion
- `experiment`: Lazy-loading experiment API
- `oect_transfer`: Transfer characteristics analysis
- `features`: V1 feature storage (HDF5)
- `features_version`: V1 feature workflows
- `features_v2`: Advanced feature engineering (Parquet)
- `visualization`: Plotting and animation
- `catalog`: Unified data management
- `stability_report`: Report generation

---

## Version History Summary

- **1.0.7** (2025-11-01): Bug fixes for V1/V2 feature extraction
- **1.0.6** (2025-01-11): Initial PyPI release
- **1.0.0 - 1.0.5**: Internal development versions

[1.0.7]: https://github.com/Durian-leader/oect-infra-package/compare/v1.0.6...v1.0.7
[1.0.6]: https://github.com/Durian-leader/oect-infra-package/releases/tag/v1.0.6
