#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
CONFIG_FILE="pyproject.toml"

# --- Script Logic ---

# 1. Check for new version argument
if [ -z "$1" ]; then
  echo "Error: No version number supplied."
  echo "Usage: ./release.sh <new-version>"
  exit 1
fi

NEW_VERSION=$1
echo "🚀 Starting release process for version $NEW_VERSION..."

# Clean up file format (remove Windows CRLF if present)
echo "🔧 Ensuring consistent file format..."
sed -i 's/\r$//' $CONFIG_FILE 2>/dev/null || true

# 2. Update version in pyproject.toml
echo "🔍 Finding current version in $CONFIG_FILE..."
# Extract version and remove any trailing whitespace/carriage returns
CURRENT_VERSION=$(grep '^version = ' $CONFIG_FILE | sed -E 's/version = "([^"]+)"/\1/' | tr -d '\r' | xargs)
if [ -z "$CURRENT_VERSION" ]; then
    echo "❌ Error: Could not find the version string in $CONFIG_FILE."
    exit 1
fi
echo "Found current version: $CURRENT_VERSION"

# Check if new version is different from current
if [ "$CURRENT_VERSION" = "$NEW_VERSION" ]; then
    echo "⚠️  Warning: New version ($NEW_VERSION) is the same as current version."
    echo "Proceeding with rebuild and upload..."
fi

echo "🔄 Updating version in $CONFIG_FILE to $NEW_VERSION..."
sed -i "s/^version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" $CONFIG_FILE

# Verify the version was updated
UPDATED_VERSION=$(grep '^version = ' $CONFIG_FILE | sed -E 's/version = "([^"]+)"/\1/' | tr -d '\r' | xargs)
if [ "$UPDATED_VERSION" != "$NEW_VERSION" ]; then
    echo "❌ Error: Version update failed. Expected $NEW_VERSION but got $UPDATED_VERSION"
    echo "Debug: Current line in file: $(grep '^version = ' $CONFIG_FILE)"
    exit 1
fi
echo "✅ Version updated successfully: $CURRENT_VERSION → $NEW_VERSION"

# 3. Clean up old builds
echo "🧹 Cleaning up old build artifacts..."
rm -rf build/ dist/ *.egg-info/
echo "✅ Cleanup complete."

# 4. Build the package using modern build system
echo "📦 Building source and wheel distributions..."
python3 -m build
echo "✅ Build successful. New packages are in dist/:"
ls -l dist

# 5. Upload to PyPI
echo "☁️  Uploading to PyPI..."
echo "Make sure you have 'twine' installed (pip install twine) and your ~/.pypirc is configured."
twine upload dist/*

echo "🎉 Successfully published version $NEW_VERSION to PyPI!"
