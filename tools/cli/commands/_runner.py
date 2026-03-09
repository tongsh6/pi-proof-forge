from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from importlib import import_module


def run_legacy_main(module_name: str, argv: Sequence[str] | None = None) -> int:
    module = import_module(module_name)
    main_func = getattr(module, "main")
    original_argv = sys.argv[:]
    if argv is not None:
        sys.argv = [module_name.split(".")[-1] + ".py", *argv]
    original_force_legacy = os.environ.get("PPF_FORCE_LEGACY_MAIN")
    os.environ["PPF_FORCE_LEGACY_MAIN"] = "1"
    try:
        result = main_func()
        if result is None:
            return 0
        return int(result)
    finally:
        sys.argv = original_argv
        if original_force_legacy is None:
            os.environ.pop("PPF_FORCE_LEGACY_MAIN", None)
        else:
            os.environ["PPF_FORCE_LEGACY_MAIN"] = original_force_legacy
