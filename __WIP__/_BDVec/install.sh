#!/usr/bin/env bash
set -euo pipefail

echo ""
echo " ============================================"
echo "  BDVE Embedder Demo — Environment Setup"
echo " ============================================"
echo ""

# Resolve to _showcase directory regardless of where the script is called from
cd "$(dirname "$0")"

# Check Python is available
if ! command -v python3 &> /dev/null; then
    echo " [ERROR] python3 not found. Please install Python 3.11+."
    exit 1
fi

# Create isolated virtual environment
if [ ! -d ".venv" ]; then
    echo " [1/3] Creating isolated virtual environment..."
    python3 -m venv .venv
    echo "       Done."
else
    echo " [1/3] Virtual environment already exists — skipping."
fi

# Activate and install dependencies
echo " [2/3] Installing dependencies..."
source .venv/bin/activate

# Upgrade pip and setuptools first to avoid build-backend issues
python -m pip install --upgrade pip setuptools wheel --quiet

pip install -r requirements.txt --quiet

# Install the bpe_svd package with training extras (inference + training).
# The [training] extra includes scipy for the SVD compression step.
pip install -e "../packages/bpe_svd[training]" --quiet || \
    echo " [WARN] Could not install bpe_svd package. Demo stubs will still work."
echo "       Done."

echo " [3/3] Verifying installation..."
python -c "import numpy; print(f'       numpy {numpy.__version__}')"
python -c "import scipy; print(f'       scipy {scipy.__version__}')"
python -c "import tkinter; print('       tkinter OK')"
python -c "import bpe_svd; print(f'       bpe_svd {bpe_svd.__version__}')" 2>/dev/null || \
    echo "       bpe_svd not installed (optional)"

echo ""
echo " ============================================"
echo "  Setup complete."
echo ""
echo "  Run the demo:"
echo "    ./run_ui.sh        (graphical interface)"
echo "    ./run_cli.sh       (command line)"
echo " ============================================"
echo ""
