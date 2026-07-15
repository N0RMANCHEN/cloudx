from __future__ import annotations

import os
import pathlib
import stat
import sys
import tempfile
import unittest
import pkgutil
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local"))

from cloudx_local.accounts import current_account, list_accounts, parser, shell_exit, shell_select  # noqa: E402
from cloudx_local.accounts import main as accounts_main  # noqa: E402
from cloudx_local.config import LocalConfig  # noqa: E402
from cloudx_local.profile import cloud_codex_environment, prepare_cloud_codex_home  # noqa: E402


class AccountAndProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name)
        self.environment = mock.patch.dict(
            os.environ,
            {
                "CLOUDX_USER_HOME": str(self.home),
                "CLOUDX_DISABLE_UPDATE_CHECK": "1",
                "CODEXX_ACTIVE_ACCOUNT": "",
            },
            clear=False,
        )
        self.environment.start()
        self.config = LocalConfig.load()
        for name in ("soul0", "soul1"):
            (self.config.accounts_dir / name / ".codex").mkdir(parents=True)
        (self.home / ".codex").mkdir()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp.cleanup()

    def test_shell_selection_and_exit(self) -> None:
        output = shell_select(self.config, "soul0")
        self.assertIn("CODEX_HOME", output)
        self.assertIn("CODEXX_ACTIVE_ACCOUNT=soul0", output)
        with mock.patch.dict(os.environ, {"CODEXX_ACTIVE_ACCOUNT": "soul0"}, clear=False):
            self.assertEqual(current_account(self.config), "soul0")
            self.assertEqual(list_accounts(self.config), ["soul0", "soul1"])
        self.assertIn("unset CODEX_HOME", shell_exit(self.config))

    def test_shell_hook_preserves_codexx_use_compatibility(self) -> None:
        hook = pkgutil.get_data("cloudx_local", "data/cloudx.zsh")
        self.assertIsNotNone(hook)
        text = hook.decode("utf-8") if hook else ""
        self.assertIn("use)", text)
        self.assertIn('_mode account "$2" --shell-pid "$$"', text)
        self.assertIn('_mode cloud --shell-pid "$$"', text)
        self.assertIn("use", parser().format_help())
        self.assertIn("codexx <account>", parser().format_help())

    def test_account_rename_and_reversible_remove(self) -> None:
        self.assertEqual(accounts_main(["rename", "soul1", "work"]), 0)
        self.assertIn("work", list_accounts(self.config))
        self.assertNotIn("soul1", list_accounts(self.config))
        self.assertEqual(accounts_main(["remove", "work"]), 0)
        self.assertNotIn("work", list_accounts(self.config))
        archived = list((self.config.state_dir / "account-archive").glob("*-work/.codex"))
        self.assertEqual(len(archived), 1)

    def test_legacy_account_home_does_not_become_cloudx_user_home(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"CLOUDX_USER_HOME": "", "CODEXX_USER_HOME": str(self.home), "HOME": str(self.home / "account-home")},
            clear=False,
        ):
            self.assertEqual(LocalConfig.load().home, self.home)

    def test_cloud_profile_shares_only_declared_entries(self) -> None:
        target = prepare_cloud_codex_home(self.config)
        for name in ("sessions", "session_index.jsonl", "skills"):
            self.assertTrue((target / name).is_symlink())
        self.assertFalse((target / "config.toml").exists())
        self.assertFalse((target / "auth.json").exists())

    def test_cloud_environment_is_process_scoped(self) -> None:
        with mock.patch.dict(os.environ, {"HTTP_PROXY": "http://bad", "CODEXX_ACTIVE_ACCOUNT": "cloud"}, clear=False):
            environment = cloud_codex_environment(self.config, "private-key", 24567)
        self.assertEqual(environment["OPENAI_BASE_URL"], "http://127.0.0.1:24567/v1")
        self.assertEqual(environment["OPENAI_API_KEY"], "private-key")
        self.assertNotIn("HTTP_PROXY", environment)
        self.assertNotIn("CODEXX_ACTIVE_ACCOUNT", environment)
        auth = self.config.cloud_codex_home / "auth.json"
        self.assertEqual(stat.S_IMODE(auth.stat().st_mode), 0o600)
        self.assertIn("private-key", auth.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
