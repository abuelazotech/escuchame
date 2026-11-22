from __future__ import annotations

import argparse
import fcntl
import os
import signal
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore

try:
    from .ui import ControlVozApp
except ImportError:  # ejecución directa
    from control_voz.ui import ControlVozApp


_LOCK_HANDLE = None


def _acquire_single_instance() -> bool:
    global _LOCK_HANDLE
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    path = Path(runtime) / "control-voz.lock"
    handle = path.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    handle.write(str(os.getpid()))
    handle.flush()
    _LOCK_HANDLE = handle
    return True


def main():
    parser = argparse.ArgumentParser(description="Escúchame: control por voz para Linux Mint Cinnamon")
    parser.add_argument("--version", action="store_true", help="Mostrar versión")
    args = parser.parse_args()
    if args.version:
        from . import __version__
        print(f"control-voz {__version__}")
        return 0

    if not _acquire_single_instance():
        print("Escúchame ya está en ejecución.")
        return 0

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = ControlVozApp()
    try:
        Gtk.main()
    except KeyboardInterrupt:
        app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
