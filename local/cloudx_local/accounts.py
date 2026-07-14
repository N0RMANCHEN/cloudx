from __future__ import annotations

import argparse
import json
import os
import pathlib
import pkgutil
import re
import shlex
import subprocess
import sys
from typing import Dict, List, Optional, Sequence

from .config import LocalConfig
from .files import atomic_json, ensure_private_directory


ACCOUNT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def account_home(config: LocalConfig, name: str) -> pathlib.Path:
    if not ACCOUNT_NAME.match(name):
        raise RuntimeError("account name must use letters, digits, dot, underscore, or hyphen")
    return config.accounts_dir / name / ".codex"


def list_accounts(config: LocalConfig) -> List[str]:
    if not config.accounts_dir.is_dir():
        return []
    names = []
    for path in config.accounts_dir.iterdir():
        if path.is_dir() and (path / ".codex").is_dir() and ACCOUNT_NAME.match(path.name):
            names.append(path.name)
    return sorted(names, key=str.casefold)


def state_path(config: LocalConfig) -> pathlib.Path:
    return config.state_dir / "accounts.json"


def read_state(config: LocalConfig) -> Dict[str, str]:
    path = state_path(config)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def current_account(config: LocalConfig) -> str:
    del config
    return os.environ.get("CODEXX_ACTIVE_ACCOUNT", "").strip()


def last_selected_account(config: LocalConfig) -> str:
    return str(read_state(config).get("lastSelected") or "")


def shell_select(config: LocalConfig, name: str) -> str:
    home = account_home(config, name)
    if not home.is_dir():
        raise RuntimeError("unknown account: %s" % name)
    atomic_json(state_path(config), {"lastSelected": name})
    values = {
        "HOME": str(config.home),
        "CODEX_HOME": str(home),
        "CODEXX_ACTIVE_ACCOUNT": name,
        "CODEXX_ACTIVE_HOME": str(home),
        "CODEXX_ACTIVE_PINNED": "1",
    }
    lines = ["export %s=%s" % (key, shlex.quote(value)) for key, value in values.items()]
    lines.extend("unset %s" % name for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"))
    return "\n".join(lines)


def shell_exit(config: LocalConfig) -> str:
    lines = ["export HOME=%s" % shlex.quote(str(config.home))]
    lines.extend(
        "unset %s" % name
        for name in (
            "CODEX_HOME",
            "CODEXX_ACTIVE_ACCOUNT",
            "CODEXX_ACTIVE_HOME",
            "CODEXX_ACTIVE_PINNED",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_API_BASE",
        )
    )
    return "\n".join(lines)


def run_codex_account_command(config: LocalConfig, name: str, args: Sequence[str]) -> int:
    home = account_home(config, name)
    if not home.is_dir():
        raise RuntimeError("unknown account: %s" % name)
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(home)
    environment.pop("CODEXX_SHARED_CODEX_ROOT", None)
    for variable in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"):
        environment.pop(variable, None)
    try:
        return int(subprocess.run([config.codex_binary, *args], env=environment, check=False).returncode)
    except FileNotFoundError as exc:
        raise RuntimeError("official Codex executable was not found: %s" % config.codex_binary) from exc


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="codexx")
    sub = root.add_subparsers(dest="command")
    add = sub.add_parser("add")
    add.add_argument("name")
    for command in ("login", "status", "logout"):
        item = sub.add_parser(command)
        item.add_argument("name", nargs="?")
    sub.add_parser("list")
    sub.add_parser("current")
    sub.add_parser("exit")
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    config = LocalConfig.load()
    if arguments[:1] == ["shell-hook"]:
        if arguments not in (["shell-hook", "zsh"], ["shell-hook", "bash"]):
            raise RuntimeError("shell-hook compatibility supports zsh or bash")
        data = pkgutil.get_data("cloudx_local", "data/cloudx.zsh")
        if not data:
            raise RuntimeError("Cloudx shell hook is missing")
        sys.stdout.write(data.decode("utf-8"))
        return 0
    if arguments[:1] == ["has-account"]:
        if len(arguments) != 2:
            return 2
        return 0 if account_home(config, arguments[1]).is_dir() else 1
    if arguments[:1] == ["use"]:
        if len(arguments) < 2:
            raise RuntimeError("use compatibility requires an account name")
        print(shell_select(config, arguments[1]))
        return 0
    if arguments == ["resolve-codex-bin"]:
        print(config.codex_binary)
        return 0
    if len(arguments) == 1 and arguments[0] not in {"add", "login", "status", "logout", "list", "current", "exit", "-h", "--help"}:
        print(shell_select(config, arguments[0]))
        return 0
    args = parser().parse_args(arguments)
    if args.command == "add":
        home = account_home(config, args.name)
        if home.exists():
            raise RuntimeError("account already exists: %s" % args.name)
        ensure_private_directory(home)
        print(args.name)
        return 0
    if args.command in ("login", "status", "logout"):
        name = args.name or current_account(config) or last_selected_account(config)
        if not name:
            raise RuntimeError("select an account or pass its name")
        command_args = {
            "login": ["login"],
            "status": ["login", "status"],
            "logout": ["logout"],
        }[args.command]
        return run_codex_account_command(config, name, command_args)
    if args.command == "list":
        selected = current_account(config)
        for name in list_accounts(config):
            print(("* " if name == selected else "  ") + name)
        return 0
    if args.command == "current":
        print(current_account(config) or "-")
        return 0
    if args.command == "exit":
        print(shell_exit(config))
        return 0
    parser().print_help()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("codexx: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
