from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Sequence

from . import accounts, api_diagnosis, cloud_cli, import_ui, local_cpa, local_cpa_maintenance, modes
from .config import LocalConfig


def _print_help() -> None:
    print(
        """usage: codexx <command> [arguments]

Modes (current shell):
  codexx api                       select the local API/CPA profile
  codexx cpa                       select the local CPA compatibility profile
  codexx cloud                     select the cloud gateway profile
  codexx <account>                 select a named local Codex account
  codexx exit                      return to the native profile

Account lifecycle:
  codexx add|login|status|logout|list|current|remove|rename ...

Credential import:
  codexx import <source> [options]  import through the external local CPA adapter
    --dry-run                       validate and preview without writing
    --json                          emit cloudx.local-cpa-import.v1
  codexx cloud import <source>      import through SSH to the cloud gateway

API failure diagnosis (read-only):
  codexx diagnose [api|cpa|cloud] [--json]
  codexx api diagnose [--json]
  codexx cloud diagnose [--json]

Local CPA credential maintenance:
  codexx api refresh [--dry-run|--apply] [--json]
  codexx api restore <archived-file> --confirm <archived-file>

After selecting a mode, run plain `codex`; it remains the installed official executable."""
    )


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
    if not arguments or arguments in (["-h"], ["--help"]):
        _print_help()
        return 0
    if arguments[:1] == ["_mode"]:
        return _mode(arguments[1:])
    if arguments[:2] == ["cloud", "import"]:
        return cloud_cli.main(["import", *arguments[2:]])
    if arguments[:2] == ["cloud", "diagnose"]:
        return api_diagnosis.run(LocalConfig.load(), arguments[2:], forced_target="cloud")
    if len(arguments) >= 2 and arguments[0] in ("api", "cpa") and arguments[1] == "diagnose":
        return api_diagnosis.run(LocalConfig.load(), arguments[2:], forced_target=arguments[0])
    if len(arguments) >= 2 and arguments[0] in ("api", "cpa") and arguments[1] == "refresh":
        return local_cpa_maintenance.refresh_run(LocalConfig.load(), arguments[2:])
    if len(arguments) >= 2 and arguments[0] in ("api", "cpa") and arguments[1] == "restore":
        return local_cpa_maintenance.restore_run(LocalConfig.load(), arguments[2:])
    if arguments[:1] == ["diagnose"]:
        return api_diagnosis.run(LocalConfig.load(), arguments[1:])
    if arguments[:1] == ["cloud"]:
        return _mode(["cloud", "--shell-pid", str(os.getppid())])
    if arguments[:1] == ["import"]:
        if len(arguments) < 2:
            if import_ui.human_output():
                import_ui.render(
                    import_ui.failure_report(
                        import_ui.LOCAL_CPA_DESTINATION,
                        "a local file or directory is required; usage: codexx import <source>",
                    ),
                    stream=sys.stderr,
                )
                return 2
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
