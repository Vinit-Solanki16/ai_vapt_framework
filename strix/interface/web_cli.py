"""``strix web`` command: serve the STRIX AI-VAPT operations console."""

from __future__ import annotations

import argparse
import contextlib
import ipaddress
import os
import platform
import shutil
import subprocess
import threading
import webbrowser

import uvicorn
from rich.console import Console


_LOG_LEVELS = ("critical", "error", "warning", "info", "debug", "trace")


def _is_loopback(host: str) -> bool:
    value = host.strip().lower()
    if value in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def run_web(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="strix web",
        description=(
            "Start the STRIX AI-VAPT operations console: a local FastAPI gateway "
            "serving the interactive web SPA."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to serve on (default: 8000).",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the browser automatically.",
    )
    parser.add_argument(
        "--log-level",
        default="warning",
        choices=_LOG_LEVELS,
        help="Uvicorn log level (default: warning).",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help=(
            "Permit binding to a non-loopback interface. The console has no "
            "authentication, so only do this on a trusted network."
        ),
    )
    args = parser.parse_args(argv)

    if not 1 <= args.port <= 65_535:
        parser.error("--port must be between 1 and 65535")

    console = Console()

    if not _is_loopback(args.host) and not args.allow_remote:
        console.print(
            "[bold red]Refusing to bind the console to a non-loopback interface.[/]\n"
            "The console can start scans and has no authentication. Re-run with "
            "[cyan]--allow-remote[/] only on a trusted network, or use "
            "[cyan]--host 127.0.0.1[/]."
        )
        return 2

    # Deferred so ``strix web --help`` stays light and the CLI module does not
    # import the FastAPI app (and its scanner probes) until it is needed.
    from strix.interface.api import app  # noqa: PLC0415

    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{display_host}:{args.port}/"
    console.print()
    console.print(f"Serving the [bold white]AI-VAPT Operations Console[/] at [cyan]{url}[/]")
    console.print("[dim]Press Ctrl-C to stop the gateway.[/]")
    console.print()

    if not args.no_open:

        def _open() -> None:
            # Under WSL, open via Windows host cmd.exe or wslview directly
            is_wsl = (
                os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop")
                or "microsoft" in platform.uname().release.lower()
            )
            if is_wsl:
                for cmd in ["/mnt/c/Windows/system32/cmd.exe", "cmd.exe"]:
                    if shutil.which(cmd):
                        try:
                            subprocess.run(
                                [cmd, "/c", "start", url],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                check=False,
                            )
                            return
                        except Exception:
                            pass
                if shutil.which("wslview"):
                    try:
                        subprocess.run(
                            ["wslview", url],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False,
                        )
                        return
                    except Exception:
                        pass

            # Native desktop browser: suppress stderr to prevent gio noise on headless systems
            with contextlib.suppress(Exception), open(os.devnull, "w") as devnull:
                old_stderr = os.dup(2)
                try:
                    os.dup2(devnull.fileno(), 2)
                    webbrowser.open(url)
                finally:
                    os.dup2(old_stderr, 2)
                    os.close(old_stderr)

        threading.Timer(1.0, _open).start()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )
    return 0


__all__ = ["run_web"]
