"""Shared limits and the Abaqus guard for offline plate forward tests. All data here is SYNTHETIC."""

from __future__ import annotations

import os
import subprocess
from unittest import mock

from domain.plate_material_problem import EvidenceKind, ForwardProvenance, ResourceLimits


# Development resource caps declared before testing. They are not scientific tolerances.
TEST_LIMITS = ResourceLimits(
    max_dofs=225,
    max_allocation_bytes=64 * 1024 * 1024,
    max_package_file_bytes=2 * 1024 * 1024,
    max_package_uncompressed_bytes=8 * 1024 * 1024,
    max_manifest_bytes=256 * 1024,
    max_matrix_nonzeros=10_000,
    max_matrix_dofs=64,
)
SYNTHETIC = ForwardProvenance(EvidenceKind.SYNTHETIC, "synthetic unit-test input; no specimen and no measurement")


def _attempted_external_process(*args, **kwargs):
    raise AssertionError(f"An offline forward test attempted to start a process: {args!r}")


def _attempted_abaqus(*args, **kwargs):
    raise AssertionError("An offline forward test attempted an Abaqus path.")


class AbaqusForbiddenMixin:
    """Make any attempted process launch or Abaqus service call fail the test."""

    def setUp(self) -> None:
        super().setUp()
        targets = [
            mock.patch.object(subprocess, "Popen", _attempted_external_process),
            mock.patch.object(os, "system", _attempted_external_process),
            mock.patch("services.matrix_model_service.run_abaqus_matrix_job", _attempted_abaqus),
            mock.patch("services.matrix_model_service.evaluate_stage_a_abaqus_point", _attempted_abaqus),
        ]
        for patcher in targets:
            patcher.start()
            self.addCleanup(patcher.stop)
