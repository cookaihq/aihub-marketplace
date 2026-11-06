"""Start configuration/artifact services through the Plugin's pinned Python environment."""
from pathlib import Path
import sys
from _runtime_bootstrap import ensure_runtime

PACKAGE = Path(__file__).resolve().parent.parent
ensure_runtime('AIHUB_STUDIO_UI_BOOTSTRAP_REEXEC', project=PACKAGE)
sys.path.insert(0, str(PACKAGE / 'ui'))
from launcher import main

if __name__ == '__main__':
    main(PACKAGE, 'aihub-studio')
