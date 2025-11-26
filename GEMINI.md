# GEMINI.md

## Project Overview

This project, `oect-infra`, is a comprehensive Python-based data processing infrastructure designed for OECT (Organic Electrochemical Transistor) experiments. It provides an end-to-end platform for transforming raw experimental data into structured formats, with capabilities for feature engineering, data visualization, and automated reporting.

The architecture is layered, separating core data processing from higher-level application and integration logic. Key data formats include HDF5 for raw and V1 feature data, and Parquet for V2 features. A central SQLite database acts as a data catalog to index and manage experiment metadata.

**Main Technologies:**
- **Language:** Python 3.11+
- **Core Libraries:** `h5py`, `pandas`, `numpy`, `pydantic`, `pyarrow`
- **CLI:** Implemented using Python's `argparse`.
- **Packaging:** `setuptools` and `pyproject.toml`.

## Building and Running

The project is a Python package and can be installed via `pip`.

### Installation

```bash
pip install .
```

Or for development (enables editing):

```bash
pip install -e .
```

### Running the Application

The primary interface is a command-line tool named `catalog`. It provides subcommands for most of the core functionality.

**Key Commands:**

1.  **Initialize the system:**
    *   This command sets up the configuration file (`catalog_config.yaml`) and the database.
    ```bash
    catalog init --auto-config
    ```

2.  **Scan for data files:**
    *   Scans specified directories for HDF5 files and adds them to the database.
    ```bash
    catalog scan --path data/raw --recursive
    ```

3.  **Synchronize metadata:**
    *   Performs a bidirectional sync between the database and the HDF5 files.
    ```bash
    catalog sync --direction both
    ```

4.  **Query experiments:**
    *   Search for experiments based on various criteria.
    ```bash
    catalog query --chip "#20250804008" --output table
    ```

5.  **Extract V2 Features:**
    *   Run the V2 feature extraction pipeline.
    ```bash
    catalog v2 extract-batch --feature-config v2_ml_ready --workers 4
    ```

### Running Tests

The project uses `pytest` for testing.

```bash
pytest
```

## Development Conventions

- **Code Style:** The project appears to follow standard Python conventions (PEP 8).
- **Configuration:** Project and data paths are managed via a central `catalog_config.yaml` file.
- **Entry Points:** The main functionalities are exposed as command-line scripts defined in `pyproject.toml`.
- **Modularity:** The codebase is organized into distinct modules within the `infra/` directory, such as `catalog`, `experiment`, `features_v2`, etc., promoting a clear separation of concerns.
