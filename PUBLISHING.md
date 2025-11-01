# Publishing Guide for OECT-Infra

This guide provides step-by-step instructions for building and publishing the `oect-infra` package to PyPI.

## Prerequisites

### 1. PyPI Account Setup

If you haven't already:
1. Create an account at [https://pypi.org/account/register/](https://pypi.org/account/register/)
2. Verify your email address
3. Enable 2FA (Two-Factor Authentication) for security

### 2. Create API Token

1. Go to [https://pypi.org/manage/account/](https://pypi.org/manage/account/)
2. Scroll to "API tokens" section
3. Click "Add API token"
4. Name: `oect-infra-upload` (or any descriptive name)
5. Scope: Select "Entire account" or "Project: oect-infra" (after first upload)
6. Copy the token (starts with `pypi-`)
7. **Important**: Save this token securely - you won't be able to see it again!

### 3. Configure PyPI Credentials

Create or edit `~/.pypirc`:

```ini
[pypi]
username = __token__
password = pypi-YOUR_TOKEN_HERE
```

Or use environment variable:
```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-YOUR_TOKEN_HERE
```

## Installation of Build Tools

Install the required build and upload tools:

```bash
# Using pip
pip install --upgrade build twine

# Or using conda
conda install -c conda-forge build twine
```

## Pre-Publishing Checklist

Before publishing, verify:

- [ ] Version number is updated in `pyproject.toml`
- [ ] README.md is up-to-date
- [ ] CHANGELOG or release notes are prepared (optional)
- [ ] All tests pass (if you have tests)
- [ ] Documentation is current
- [ ] License file is present

## Building the Package

### 1. Navigate to Package Directory

```bash
cd /home/lidonghaowsl/develop/Minitest-OECT-dataprocessing/oect-infra-package
```

### 2. Clean Previous Builds (if any)

```bash
rm -rf dist/ build/ *.egg-info
```

### 3. Build Distribution Files

```bash
python -m build
```

This creates two files in the `dist/` directory:
- `oect_infra-1.0.0.tar.gz` (source distribution)
- `oect_infra-1.0.0-py3-none-any.whl` (wheel distribution)

### 4. Verify Build Contents

Check what files are included:

```bash
# For wheel
unzip -l dist/oect_infra-1.0.0-py3-none-any.whl

# For source distribution
tar -tzf dist/oect_infra-1.0.0.tar.gz
```

## Testing the Package

### 1. Check Package Validity

```bash
twine check dist/*
```

Expected output: `PASSED` for all distributions

### 2. Test Installation Locally

```bash
# Create a test virtual environment
python -m venv test_env
source test_env/bin/activate  # On Windows: test_env\Scripts\activate

# Install from the wheel
pip install dist/oect_infra-1.0.0-py3-none-any.whl

# Test import
python -c "from infra.catalog import UnifiedExperimentManager; print('Import successful!')"

# Test CLI
catalog --help
stability-report --help

# Deactivate and remove test environment
deactivate
rm -rf test_env
```

### 3. Test on TestPyPI (Recommended)

Upload to TestPyPI first to verify everything works:

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Install from TestPyPI to verify
pip install --index-url https://test.pypi.org/simple/ --no-deps oect-infra

# Test the installation
python -c "import infra; print(infra.__version__)"
```

## Publishing to PyPI

### Upload to Production PyPI

Once you've verified everything works:

```bash
twine upload dist/*
```

You'll see output like:
```
Uploading distributions to https://upload.pypi.org/legacy/
Uploading oect_infra-1.0.0-py3-none-any.whl
100%|████████████████████| 1.23M/1.23M [00:02<00:00, 512kB/s]
Uploading oect_infra-1.0.0.tar.gz
100%|████████████████████| 987k/987k [00:01<00:00, 678kB/s]

View at:
https://pypi.org/project/oect-infra/1.0.0/
```

## Post-Publishing Steps

### 1. Verify Installation

```bash
# Wait 1-2 minutes for PyPI to process
pip install oect-infra

# Verify version
python -c "import infra; print(infra.__version__)"
```

### 2. Test in Fresh Environment

```bash
python -m venv fresh_test
source fresh_test/bin/activate
pip install oect-infra
python -c "from infra.catalog import quick_start; print('Success!')"
deactivate
rm -rf fresh_test
```

### 3. Update Repository

```bash
# Tag the release in git
cd /home/lidonghaowsl/develop/Minitest-OECT-dataprocessing
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0

# Update main README to mention PyPI availability
```

## Versioning Strategy

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.x.x): Incompatible API changes
- **MINOR** (x.1.x): Add functionality (backwards-compatible)
- **PATCH** (x.x.1): Bug fixes (backwards-compatible)

For future releases:
1. Update version in `pyproject.toml`
2. Update changelog
3. Rebuild and reupload

## Troubleshooting

### Error: "The user isn't allowed to upload"
- Verify your API token is correct
- Check token scope includes the project

### Error: "File already exists"
- Each version can only be uploaded once
- Increment version number in `pyproject.toml`
- Rebuild and try again

### Error: "Invalid distribution file"
- Run `twine check dist/*` to identify issues
- Common: Missing README.md or invalid metadata

### Import Errors After Installation
- Check package structure with `unzip -l dist/*.whl`
- Verify `__init__.py` files exist in all directories
- Check `MANIFEST.in` includes necessary files

## Updating an Existing Package

To release a new version:

```bash
# 1. Update version in pyproject.toml
# 2. Clean old builds
rm -rf dist/ build/ *.egg-info

# 3. Build new version
python -m build

# 4. Upload
twine upload dist/*
```

## Security Best Practices

1. **Never commit API tokens** to version control
2. Use `.pypirc` with restricted permissions: `chmod 600 ~/.pypirc`
3. Enable 2FA on PyPI account
4. Use project-scoped tokens when possible
5. Rotate tokens periodically

## Resources

- PyPI Documentation: https://packaging.python.org/
- Twine Documentation: https://twine.readthedocs.io/
- Python Packaging Guide: https://packaging.python.org/tutorials/packaging-projects/
- Setuptools Documentation: https://setuptools.pypa.io/

## Support

If you encounter issues:
1. Check the [Python Packaging Guide](https://packaging.python.org/)
2. PyPI support: https://pypi.org/help/
3. GitHub Issues: https://github.com/Durian-leader/oect-infra-package/issues

---

**Last Updated**: 2025-11-01
**Package**: oect-infra v1.0.7
