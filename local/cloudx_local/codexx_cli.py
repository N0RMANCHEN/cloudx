from __future__ import annotations

import argparse
import os
from typing import Optional, Sequence

from . import accounts, cloud_cli, local_cpa, modes
from .config import LocalConfig


def _mode(arguments: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="codexx mode")
    parser.add_argument("mode", choices=("account", "cloud", "exit"))
    parser.add_argument("name", nargs="?")
    parser.add_argument("--shell-pid", type=int, default=os.getppid())
    args = parser.parse_args(list(arguments))
    config = LocalConfig.load()
    if args.mode == "cloud":
        if args.name:
            raise RuntimeError("cloud mode does not accept an account name")
        print(modes.select_cloud(config, args.shell_pid))
    elif args.mode == "account":
        if not args.name:
            raise RuntimeError("account mode requires an account name")
        print(modes.select_account(config, args.name))
    else:
        if args.name:
            raise RuntimeError("exit mode does not accept an account name")
        print(modes.exit_mode(config))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(argv or [])
    if arguments[:1] == ["_mode"]:
        return _mode(arguments[1:])
    if arguments[:2] == ["cloud", "import"]:
        return cloud_cli.main(["import", *arguments[2:]])
    if arguments[:1] == ["cloud"]:
        return _mode(["cloud", "--shell-pid", str(os.getppid())])
    if arguments[:1] == ["import"]:
        if len(arguments) < 2:
            raise RuntimeError("local CPA import requires a local file or directory")
        return local_cpa.import_local(LocalConfig.load(), arguments[1], arguments[2:])
    if arguments == ["exit"]:
        print(modes.exit_mode(LocalConfig.load()))
        return 0
    if arguments[:1] == ["use"]:
        if len(arguments) != 2:
            raise RuntimeError("use requires exactly one account name")
        print(modes.select_account(LocalConfig.load(), arguments[1]))
        return 0
    lifecycle = {"add", "login", "status", "logout", "list", "current", "remove", "rename", "-h", "--help"}
    if len(arguments) == 1 and arguments[0] not in lifecycle:
        print(modes.select_account(LocalConfig.load(), arguments[0]))
        return 0
    return accounts.main(arguments)
