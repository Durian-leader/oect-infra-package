# csv2hdf package
"""
Direct CSV to HDF5 conversion utilities for scientific test data processing.

This package provides optimized direct conversion from CSV and JSON test data 
to HDF5 format with high-performance multiprocessing capabilities.

Features:
- Direct CSV+JSON to HDF5 conversion with new optimized format
- Multiprocessing support for faster CSV processing  
- Batch processing of multiple experiments
- JSON cleaning and validation utilities
"""

from .batch_csvjson2hdf import process_folders_parallel
from .clean_json import batch_clean_json_files
from .direct_csv2hdf import (
    direct_convert_csvjson_to_hdf5,
    direct_csv_to_new_hdf5_parallel,
    direct_csv_to_new_hdf5
)
from .parallel_csv_processing import (
    parallel_process_csv_files,
    optimize_process_count
)

__all__ = [
    "process_folders_parallel",
    "batch_clean_json_files", 
    "direct_convert_csvjson_to_hdf5",
    "direct_csv_to_new_hdf5_parallel",
    "direct_csv_to_new_hdf5",
    "parallel_process_csv_files",
    "optimize_process_count"
]