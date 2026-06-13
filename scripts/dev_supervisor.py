#!/usr/bin/env python3
"""Supervise a long-running dev process and rotate its output into a log file.

The command is spawned in its own process group so that the whole tree (e.g.
uvicorn's reloader + worker, or ``task tunnel`` -> ngrok) can be terminated
together. Combined stdout/stderr is streamed through a size-rotating log file,
and on SIGTERM/SIGINT the child process group is terminated before exit.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import FrameType
from typing import Annotated

import typer

_FIVE_MB = 5 * 1024 * 1024

app = typer.Typer(
    add_completion=False,
    context_settings={"ignore_unknown_options": True},
    help=__doc__,
)


def _build_logger(log_file: Path, max_bytes: int, backups: int) -> logging.Logger:
    handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("tiberio.dev_supervisor")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


@app.command()
def main(
    command: Annotated[
        list[str],
        typer.Argument(help="Command to supervise, preceded by '--'."),
    ],
    log_file: Annotated[
        Path,
        typer.Option("--log-file", help="Target rotating log file."),
    ],
    max_bytes: Annotated[
        int,
        typer.Option(
            "--max-bytes", help="Rotate once the log exceeds this size in bytes."
        ),
    ] = _FIVE_MB,
    backups: Annotated[
        int,
        typer.Option("--backups", help="Number of rotated log files to keep."),
    ] = 5,
    pgid_file: Annotated[
        Path | None,
        typer.Option("--pgid-file", help="File to write the child process group id."),
    ] = None,
) -> None:
    """Run COMMAND, rotating its combined output into LOG_FILE."""
    argv = [part for part in command if part != "--"]
    if not argv:
        raise typer.BadParameter("a command to supervise is required (after '--')")

    logger = _build_logger(log_file, max_bytes, backups)

    process = subprocess.Popen(  # noqa: S603 — supervising an explicit dev command is this script's purpose
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
        bufsize=1,
    )

    if pgid_file is not None:
        pgid_file.write_text(str(process.pid), encoding="utf-8")

    def _terminate(_signum: int, _frame: FrameType | None) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, _terminate)
    signal.signal(signal.SIGINT, _terminate)

    assert process.stdout is not None
    for line in process.stdout:
        logger.info(line.rstrip("\n"))

    raise typer.Exit(code=process.wait())


if __name__ == "__main__":
    app()
