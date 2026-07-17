from __future__ import annotations

import copy
import json
import pathlib
import unittest

from scripts.check_architecture import check_cloud_public_output_guards, check_phi_mesh_topology


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOPOLOGY = ROOT / "config/governance/phi_mesh_topology.v1.json"


class GovernanceTests(unittest.TestCase):
    def topology(self) -> dict[str, object]:
        return json.loads(TOPOLOGY.read_text(encoding="utf-8"))

    def test_initial_phi_mesh_topology_is_frozen(self) -> None:
        topology = self.topology()
        self.assertEqual(check_phi_mesh_topology(topology), [])
        self.assertEqual(topology["normal_cloudx_consumers"], ["phi_cloud"])
        self.assertFalse(topology["direct_device_to_cloudx"])
        self.assertFalse(topology["cloudx_mesh_control_plane"])

    def test_topology_gate_rejects_direct_device_access(self) -> None:
        topology = copy.deepcopy(self.topology())
        topology["direct_device_to_cloudx"] = True
        self.assertTrue(check_phi_mesh_topology(topology))

    def test_topology_gate_rejects_an_additional_normal_consumer(self) -> None:
        topology = copy.deepcopy(self.topology())
        topology["normal_cloudx_consumers"] = ["phi_cloud", "trusted_device"]
        self.assertTrue(check_phi_mesh_topology(topology))

    def test_cloud_public_output_paths_are_guarded(self) -> None:
        self.assertEqual(check_cloud_public_output_guards(), [])


if __name__ == "__main__":
    unittest.main()
