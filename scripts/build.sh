#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# --------------------------------------------------------------------------- #
# Paths & constants                                                           #
# --------------------------------------------------------------------------- #
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
PROJECT_ROOT="$(realpath "$SCRIPT_DIR/..")"

BLACK="black"
BLACK_OPTS=(--line-length=88)
LINTER="flake8"
LINTER_OPTS=(--max-line-length=88 --extend-ignore=E203,W503)

GITIGNORE_URL="https://raw.githubusercontent.com/github/gitignore/main/Python.gitignore"
GITIGNORE_PATH="$PROJECT_ROOT/.gitignore"

echo "📂  Project root: $PROJECT_ROOT"

# --------------------------------------------------------------------------- #
# Update .gitignore (once every 30 days)                                      #
# --------------------------------------------------------------------------- #
if [ ! -f "$GITIGNORE_PATH" ] || find "$GITIGNORE_PATH" -mtime +30 -print -quit | grep -q .; then
    echo "🔄  Updating .gitignore"
    curl -sSfL "$GITIGNORE_URL" -o "$GITIGNORE_PATH"
fi

# --------------------------------------------------------------------------- #
# Build list of Python targets                                                #
# --------------------------------------------------------------------------- #
PY_TARGETS=("$PROJECT_ROOT/orac" "$PROJECT_ROOT/test.py")
if compgen -G "$PROJECT_ROOT/scripts/*.py" >/dev/null; then
    # shellcheck disable=SC2207
    PY_TARGETS+=($(echo "$PROJECT_ROOT"/scripts/*.py))
fi

# --------------------------------------------------------------------------- #
# Code formatting                                                             #
# --------------------------------------------------------------------------- #
echo "🎨  Running black"
$BLACK "${BLACK_OPTS[@]}" "${PY_TARGETS[@]}"

# --------------------------------------------------------------------------- #
# Linting                                                                     #
# --------------------------------------------------------------------------- #
echo "🔍  Running linter"
$LINTER "${LINTER_OPTS[@]}" "${PY_TARGETS[@]}"

echo "✅  Linting passed"

# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #
echo "🧪  Running tests"
pushd "$PROJECT_ROOT" >/dev/null
python test.py
popd >/dev/null
echo "✅  Tests passed"

# --------------------------------------------------------------------------- #
# Cleanup                                                                     #
# --------------------------------------------------------------------------- #
echo "🧹  Cleaning up"
find "$PROJECT_ROOT" -type d -name '__pycache__' -exec rm -rf {} +
find "$PROJECT_ROOT" -type d -name '*.egg-info' -exec rm -rf {} +

echo "🎉  Build successful"
# --------------------------------------------------------------------------- #
# Build & upload package                                                      #
# --------------------------------------------------------------------------- #
read -p "🚀  Build and upload package? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌  Build aborted"
    exit 1
fi

echo "📦  Building package"
python3 setup.py sdist bdist_wheel
if [ $? -ne 0 ]; then
    echo "❌  Build failed"
    exit 1
fi

echo "⬆️   Uploading package"
twine upload dist/*

echo "🎉  Build and upload successful"

exit 0
