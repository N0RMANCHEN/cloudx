from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class CiWorkflowTests(unittest.TestCase):
    def test_ci_fetches_release_tag_history_required_by_verification(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        checkout = workflow.index("uses: actions/checkout@v4")
        setup = workflow.index("uses: actions/setup-python@v5", checkout)
        checkout_block = workflow[checkout:setup]
        self.assertIn("fetch-depth: 0", checkout_block)


if __name__ == "__main__":
    unittest.main()
