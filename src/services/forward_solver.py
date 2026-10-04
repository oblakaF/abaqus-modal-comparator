"""Forward-job solve launcher — Auto-ID M4.6 (approved design, M4_DECISION_RECORD.md §6).

The only M4 module allowed to import ``subprocess``.  A solve runs the pinned solver-profile
command for one M3 forward job (content-addressed name, verified INP SHA-256) in its own job
directory and is accepted only with the profile's completion marker (``.sta``) and version
marker (``.dat``) and an ODB; the ODB is then identified by SHA-256 and size.  Failures stop
the run (``SolveFailure``) — there are no automatic retries.

The executor is injectable: tests use a fake; the default runs the command with
``subprocess`` (real Abaqus, only under a HUMAN gate).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import subprocess
from typing import Callable, Optional

from domain.identification_run import RunIdentityError, SolverProfile, canonical_hash


SolveExecutor = Callable[[str, Path], int]  # (command, job directory) -> exit code


class SolveFailure(Exception):
    """A forward solve did not complete; the run stops (no automatic retry).

    Not a ValueError/RuntimeError, so generic fallback handlers never swallow it.
    """


@dataclass(frozen=True)
class SolveRecord:
    job_name: str
    generated_inp_sha256: str
    profile_hash: str
    solve_hash: str  # canonical(generated INP SHA, profile hash): the reuse key
    odb_sha256: str
    odb_size_bytes: int
    abaqus_version_line: str
    command_template: str  # the profile template (machine paths are never recorded)

    def to_dict(self) -> dict:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


def solve_hash(generated_inp_sha256: str, profile: SolverProfile) -> str:
    return canonical_hash({"generated_inp_sha256": generated_inp_sha256, "profile_hash": profile.profile_hash})


def subprocess_executor(timeout_seconds: int = 7200) -> SolveExecutor:
    """Run the rendered command (real Abaqus — use only under an authorised HUMAN gate)."""

    def run(command: str, directory: Path) -> int:
        with open(directory / "solve.log", "w", encoding="utf-8", errors="replace") as log:
            log.write(command + "\n")
            log.flush()
            completed = subprocess.run(f'cmd.exe /d /s /c "{command}"', cwd=directory, stdout=log,
                                       stderr=subprocess.STDOUT, timeout=timeout_seconds, shell=False)
        return completed.returncode

    return run


def solve_forward_job(job, profile: SolverProfile, directory: Path, abaqus_command: str, executor: SolveExecutor,
                      scratch: Optional[Path] = None) -> SolveRecord:
    """Solve one prepared M3 forward job (``job.job_name``, ``job.generated_inp``, ``job.generated_inp_sha256``)."""

    if not job.job_name.startswith(profile.job_prefix + "_"):
        raise RunIdentityError(f"profile {profile.profile_id} is for job prefix {profile.job_prefix!r}, "
                               f"not {job.job_name}.")
    inp = Path(job.generated_inp)
    if sha256_file(inp) != job.generated_inp_sha256:
        raise RunIdentityError(f"{job.job_name}: the INP on disk differs from its M3 identity.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for path in (inp, directory) + ((Path(scratch),) if scratch is not None else ()):
        if " " in str(path):
            raise RunIdentityError(f"paths with spaces are not supported by the pinned command convention: {path}")
    command = profile.render_command(abaqus_command, job.job_name, str(inp), None if scratch is None else str(scratch))
    exit_code = executor(command, directory)
    sta, dat, odb = (directory / f"{job.job_name}{suffix}" for suffix in (".sta", ".dat", ".odb"))
    sta_text = sta.read_text(encoding="utf-8", errors="replace") if sta.exists() else ""
    dat_text = dat.read_text(encoding="utf-8", errors="replace") if dat.exists() else ""
    problems = []
    if exit_code != 0:
        problems.append(f"exit code {exit_code}")
    if profile.completion_marker not in sta_text:
        problems.append("completion marker missing in .sta")
    version_lines = [line.strip() for line in dat_text.splitlines() if profile.version_marker in line]
    if not version_lines:
        problems.append(f"{profile.version_marker!r} not found in .dat")
    if not odb.is_file():
        problems.append("no ODB")
    if problems:
        raise SolveFailure(f"{job.job_name}: solve not completed ({'; '.join(problems)}); no automatic retry.")
    return SolveRecord(job.job_name, job.generated_inp_sha256, profile.profile_hash,
                       solve_hash(job.generated_inp_sha256, profile), sha256_file(odb), odb.stat().st_size,
                       version_lines[0], profile.command_template)


def verify_solve(record: dict, directory: Path) -> Path:
    """Reuse check for a journalled solve: the ODB must still have its recorded content."""
    odb = Path(directory) / f"{record['job_name']}.odb"
    if not odb.is_file() or odb.stat().st_size != record["odb_size_bytes"] or sha256_file(odb) != record["odb_sha256"]:
        raise RunIdentityError(f"{record['job_name']}: the ODB differs from the journalled solve; not reused.")
    return odb
