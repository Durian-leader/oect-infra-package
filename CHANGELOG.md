# Changelog

All notable changes to the `oect-infra` package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2025-11-04

### Added
- **Step-Parallel Executor** ⚡ - Revolutionary parallel execution system for Features V2
  - **Architecture**: New `step_parallel_executor.py` and `task.py` modules
  - **Performance**: 200-1500x speedup vs sequential execution (48-core AMD EPYC)
  - **Features**:
    - Step-level parallelization with experiment-wide feature extraction
    - Multi-level caching (numpy arrays → pickle serialization)
    - Automatic task dependency detection and scheduling
    - Resource-aware worker pool management
  - **Documentation**:
    - `STEP_PARALLEL_ARCHITECTURE.md` - Complete architecture guide
    - `STEP_PARALLEL_REFACTOR_SUMMARY.md` - Refactoring details
    - `MIGRATION_GUIDE_STEP_PARALLEL.md` - Migration guide for users
  - **Example**: `examples/step_parallel_demo.py`

- **AutoTau Integration** 🔬 - High-performance tau extraction with autotau package
  - **New Module**: `autotau_extractors.py`
  - **Features**:
    - Simultaneous tau_on and tau_off extraction
    - Automatic workflow parameter detection (period, sample_rate)
    - Parallel cycle fitting with 200-1500x performance boost
    - Multi-step batch processing support
  - **Output Shape**: `(n_steps, n_cycles, 2)` - last dimension is [tau_on, tau_off]
  - **Dependency**: Requires `pip install autotau`

- **Context-Aware Extractors** 📊 - Enhanced feature extraction with runtime context
  - **Updated Modules**: `base.py`, `transfer.py`, `transient.py`
  - **Capabilities**:
    - Access to experiment metadata during extraction
    - Workflow parameter injection (Vg, Vd, sampling settings)
    - Context-dependent feature computation
    - Improved error handling and validation

- **Unified Manager Enhancements** 🎯
  - **Updated Module**: `catalog/unified.py`
  - **New Features**:
    - Enhanced V2 feature extraction workflow
    - Improved experiment search and filtering
    - Better cache management and cleanup
    - Workflow metadata integration

### Changed
- **Features V2 Version**: Bumped to 2.1.0 (major new features)
- **Extractor Base Class**: Now supports context injection via `get_current_context()`
- **Performance**: Significant improvements for large-scale batch processing

### Technical Details
- **Parallel Execution**: Step-parallel strategy avoids nested parallelism, maximizing CPU utilization
- **Cache Strategy**: Intermediate results cached as numpy arrays, serialized via pickle
- **AutoTau Performance**: Benchmarked at 200-1500x faster than sequential autotau calls
- **Memory Optimization**: Efficient worker pool reuse and automatic cleanup

## [1.0.10] - 2025-11-02

### Fixed
- **Transient Data Loading**: Fixed transient feature extraction in Features V2 system
  - **Root Cause**: HDF5 files lacked `start_data_index` and `end_data_index` fields in `step_info_table`, causing `KeyError` when loading transient data
  - **Fixed Files**:
    - `csv2hdf/direct_csv2hdf.py` (2 locations):
      - Line 382-404: Serial conversion - now records data index ranges for each transient step
      - Line 582-614: Parallel conversion - now records data index ranges for each transient step
    - `features_v2/core/feature_set.py`:
      - Line 106-166: `load_transient()` - smart loading with backward compatibility
        - **New Files**: Uses `step_info_table` indices for efficient array slicing (fast)
        - **Legacy Files**: Falls back to step-by-step loading with warning (slow but compatible)
  - **Impact**: Transient feature extraction now works with both new and old HDF5 files

- **Statistics Format**: Fixed `get_statistics()` return type in Features V2 executor
  - **Root Cause**: `slowest_feature` returned tuple `(name, time_ms)` instead of dict, causing `TypeError` when accessing keys
  - **Fixed Files**:
    - `features_v2/core/executor.py`:
      - Line 51-71: Now returns `{'name': str, 'time_ms': float}` dictionary format
  - **Impact**: Statistics display in notebooks and scripts now works correctly

### Added
- **Transient Feature Demo**: New comprehensive demo notebook for transient feature extraction
  - **Location**: `features_v2_transient_demo.ipynb` (repository root)
  - **Features Demonstrated**:
    - Charge integral (∫|I(t)|dt) - total charge through device
    - Peak current, decay time constant, rise time
    - Steady-state current, max response rate
    - Multi-dimensional Transient Cycles features
  - **Includes**: Data exploration, visualization, correlation analysis, config persistence

### Changed
- **Features V2 Version**: Bumped from 2.0.0 to 2.0.1 (bug fixes)
- **Backward Compatibility**: Transient loading gracefully handles legacy HDF5 files without indices

### Technical Details
- New HDF5 files track transient data ranges: `step_info_table['start_data_index']` and `['end_data_index']`
- Enables O(1) array slicing instead of O(N) step-by-step loading
- Performance: ~27 seconds to load 5000 transient steps with new format vs. potentially minutes with old approach

## [1.0.9] - 2025-11-01

### Fixed
- **V2 Feature File Naming Bug**: Fixed hardcoded 'v2_features' in file naming across all V2 feature extraction paths
  - **Root Cause**: `process_data_pipeline()` and batch extraction used hardcoded 'v2_features' string instead of actual config name
  - **Fixed Files**:
    - `catalog/unified.py` (4 locations):
      - Line 2510: `_extract_v2_wrapper()` filename generation - now uses `{config_name}` instead of hardcoded 'v2_features'
      - Line 489-495: Removed legacy `v2_features` compatibility scanning code
      - Line 489: Optimized file pattern from `v2_*-feat_*.parquet` to universal `*-feat_*.parquet`
    - `catalog/scanner.py` (2 locations):
      - Line 307: Updated file type detection to use generic Parquet pattern instead of hardcoded 'v2_features'
      - Line 350: Updated scan patterns list to use `*-feat_*.parquet`
  - **Naming Convention**: All V2 feature files now consistently use format `{chip_id}-{device_id}-{config_name}-feat_{timestamp}_{hash}.parquet`
  - **Breaking Change**: Legacy `*-v2_features-*` files are no longer recognized (requires re-extraction with correct naming)

### Impact
- File naming now correctly reflects the actual config name (e.g., `v2_ml_ready`, `v2_transfer_basic`)
- Improved cache recognition for incremental feature extraction
- Better file organization and traceability of feature configurations
- Consistent behavior between `process_data_pipeline()` and `batch_extract_features_v2()`

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
