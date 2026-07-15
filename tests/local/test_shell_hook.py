from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGED_HOOK = ROOT / "local/cloudx_local/data/cloudx.zsh"
REFERENCE_HOOK = ROOT / "local/shell/cloudx.zsh"


class ShellHookTests(unittest.TestCase):
    def test_packaged_hook_matches_reference_hook(self) -> None:
        self.assertEqual(PACKAGED_HOOK.read_bytes(), REFERENCE_HOOK.read_bytes())

    def test_zsh_right_prompt_tracks_mode_without_replacing_existing_prompt(self) -> None:
        zsh = pathlib.Path("/bin/zsh")
        if not zsh.is_file():
            self.skipTest("zsh is not available")

        with tempfile.TemporaryDirectory() as value:
            root = pathlib.Path(value)
            fake = root / "codexx"
            fake.write_text(
                """#!/bin/sh
case "$2" in
  account)
    printf 'export CODEXX_ACTIVE_ACCOUNT=%s\\n' "$3"
    ;;
  cloud)
    printf 'export CODEXX_ACTIVE_ACCOUNT=cloud\\n'
    ;;
  exit)
    printf 'unset CODEXX_ACTIVE_ACCOUNT\\n'
    ;;
  *)
    exit 2
    ;;
esac
""",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            environment = dict(os.environ)
            environment.update(
                {
                    "CLOUDX_CODEXX_BIN": str(fake),
                    "HOOK": str(PACKAGED_HOOK),
                }
            )
            for name in ("CODEXX_ACTIVE_ACCOUNT", "CLOUDX_LAST_PROMPT_SEGMENT"):
                environment.pop(name, None)
            script = r"""
RPROMPT=' [cf:one]'
source "$HOOK"
codexx api
print -r -- "step1:${RPROMPT-}"
RPROMPT=' [cf:two]'
source "$HOOK"
print -r -- "step2:${RPROMPT-}"
codexx cloud
print -r -- "step3:${RPROMPT-}"
codexx soul0
print -r -- "step4:${RPROMPT-}"
codexx exit
print -r -- "step5:${RPROMPT-}"
print -r -- "hooks:${(j:,:)precmd_functions}"
"""
            completed = subprocess.run(
                [str(zsh), "-dfc", script],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        self.assertEqual(
            completed.stdout.splitlines(),
            [
                "step1: [cf:one] [cx:api]",
                "step2: [cf:two] [cx:api]",
                "step3: [cf:two] [cx:cloud]",
                "step4: [cf:two] [cx:soul0]",
                "step5: [cf:two]",
                "hooks:__cloudx_refresh_prompt",
            ],
        )


if __name__ == "__main__":
    unittest.main()
