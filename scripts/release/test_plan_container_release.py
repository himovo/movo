#!/usr/bin/env python3

import unittest
from pathlib import Path

from plan_container_release import IMAGES, select_images


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ContainerReleasePlanTests(unittest.TestCase):
    def suffixes(self, images):
        return [image.suffix for image in images]

    def test_documentation_change_reuses_every_image(self):
        changed, unchanged = select_images(["README.md"])
        self.assertEqual([], changed)
        self.assertEqual(len(IMAGES), len(unchanged))

    def test_frontend_change_only_rebuilds_its_image(self):
        changed, _ = select_images(["apps/user-web/src/views/LoginView.vue"])
        self.assertEqual(["user-web"], self.suffixes(changed))

    def test_dsh_host_change_does_not_rebuild_chat_api(self):
        changed, _ = select_images(["services/chat-api/dsh/runtime-host/src/host.mjs"])
        self.assertEqual(["dsh-runtime-host"], self.suffixes(changed))

    def test_gateway_image_change_only_rebuilds_gateway(self):
        changed, _ = select_images(["deploy/docker/gateway.Dockerfile"])
        self.assertEqual(["gateway"], self.suffixes(changed))

    def test_chat_runtime_change_rebuilds_chat_api(self):
        changed, _ = select_images(["services/chat-api/app/runtime/runner.py"])
        self.assertEqual(["chat-api"], self.suffixes(changed))

    def test_release_workflow_change_forces_every_image(self):
        changed, unchanged = select_images([".github/workflows/container-release.yml"])
        self.assertEqual(len(IMAGES), len(changed))
        self.assertEqual([], unchanged)

    def test_force_all_rebuilds_every_image(self):
        changed, unchanged = select_images([], force_all=True)
        self.assertEqual(len(IMAGES), len(changed))
        self.assertEqual([], unchanged)

    def test_private_repository_skips_unsupported_github_attestation(self):
        workflow = (REPOSITORY_ROOT / ".github/workflows/container-release.yml").read_text()
        self.assertIn(
            "if: ${{ github.event.repository.visibility == 'public' }}\n"
            "        uses: actions/attest-build-provenance@v3",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
