from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from threading import Event
from typing import Callable, Iterable, Optional

from .constants import CANONICAL_SANDBOX_ROOT, LEGACY_SANDBOX_ROOT, SANDBOX_DIRNAME, WORKSPACE_ROOT, canonicalize_sandbox_path, sandbox_path

HOST_REPO_ROOT = Path(WORKSPACE_ROOT).resolve()
HOST_SANDBOX_ROOT = CANONICAL_SANDBOX_ROOT.resolve()
HOST_SANDBOX_APPS_ROOT = sandbox_path('apps').resolve()
CONTAINER_REPO_ROOT = PurePosixPath('/repo')
CONTAINER_WORKSPACE_ROOT = PurePosixPath('/workspace')
CONTAINER_SANDBOX_APPS_ROOT = CONTAINER_WORKSPACE_ROOT / 'apps'
CONTAINER_CATALOG_DB_PATH = CONTAINER_WORKSPACE_ROOT / 'catalog' / 'catalog.db'
DEFAULT_DOCKER_IMAGE = 'python:3.13-slim'
DEFAULT_DOCKER_EXECUTABLE = 'docker'


@dataclass
class PipelineCommand:
    label: str
    args: list[str]
    cwd: str
    display_cwd: str = ''
    display_command: str = ''
    redactions: list[tuple[str, str]] = field(default_factory=list)

    def render(self) -> str:
        return subprocess.list2cmdline([str(part) for part in self.args])

    def render_display(self) -> str:
        return self.display_command or _apply_redactions(self.render(), self.redactions)

    def prompt_line(self) -> str:
        cwd = self.display_cwd or _apply_redactions(self.cwd, self.redactions)
        return f'{cwd}> {self.render_display()}'

    def redact(self, text: str) -> str:
        return _apply_redactions(text, self.redactions)


@dataclass
class SandboxRunConfig:
    run_id: str
    template_id: str = ''
    manifest_path: str = ''
    name: str = ''
    sandbox_root: str = ''
    patch_manifests: list[str] = field(default_factory=list)
    promote_destination: str = ''
    vendor_mode: str = ''
    resolution_profile: str = ''
    force_stamp: bool = True
    backup_patches: bool = True
    promote_after: bool = True
    promote_force: bool = True
    python_executable: str = sys.executable
    execution_backend: str = 'local'
    docker_image: str = DEFAULT_DOCKER_IMAGE
    allow_host_writes: bool = False

    def resolved_sandbox_root(self) -> Path:
        return canonicalize_sandbox_path(self.sandbox_root) if self.sandbox_root else HOST_SANDBOX_APPS_ROOT

    def resolved_workspace_root(self) -> Path:
        return self.resolved_sandbox_root() / self.run_id

    def resolved_patch_manifests(self) -> list[Path]:
        return [Path(path).resolve() for path in self.patch_manifests if str(path).strip()]

    def resolved_promote_destination(self) -> Path:
        if self.promote_destination:
            return canonicalize_sandbox_path(self.promote_destination)
        return (HOST_SANDBOX_ROOT / 'promoted' / self.run_id).resolve()


def docker_preflight(docker_executable: str = DEFAULT_DOCKER_EXECUTABLE) -> dict:
    binary = shutil.which(docker_executable)
    instructions = 'Install Docker Desktop, start the Docker daemon, and confirm `docker version` succeeds before using the Docker backend.'
    if not binary:
        return {
            'available': False,
            'binary_path': '',
            'server_version': '',
            'user_message': 'Docker backend requested but Docker was not found on PATH. ' + instructions,
        }
    try:
        result = subprocess.run(
            [binary, 'version', '--format', '{{.Server.Version}}'],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        return {
            'available': False,
            'binary_path': binary,
            'server_version': '',
            'user_message': f'Docker backend requested but Docker could not be started: {exc}. {instructions}',
        }
    if result.returncode != 0 or not result.stdout.strip():
        detail = (result.stderr or result.stdout or '').strip()
        suffix = f' Details: {detail}' if detail else ''
        return {
            'available': False,
            'binary_path': binary,
            'server_version': '',
            'user_message': 'Docker backend requested but the Docker daemon is unavailable.' + suffix + ' ' + instructions,
        }
    return {
        'available': True,
        'binary_path': binary,
        'server_version': result.stdout.strip(),
        'user_message': f'Docker ready ({result.stdout.strip()}).',
    }

def build_sandbox_command_queue(config: SandboxRunConfig) -> dict:
    if not str(config.run_id).strip():
        raise ValueError('run_id is required.')
    if not str(config.template_id).strip() and not str(config.manifest_path).strip():
        raise ValueError('Provide either template_id or manifest_path.')
    workspace_root = config.resolved_workspace_root()
    patch_paths = config.resolved_patch_manifests()
    promote_destination = config.resolved_promote_destination()
    timestamp = datetime.now().strftime('%Y%m%dT%H%M%S')
    run_log_path = (HOST_SANDBOX_ROOT / 'runs' / f'{config.run_id}_{timestamp}.jsonl').resolve()
    redactions = _build_redactions(config, workspace_root, promote_destination)
    display_workspace_root = _apply_redactions(str(workspace_root), redactions)
    display_promote_destination = _apply_redactions(str(promote_destination), redactions)
    display_run_log_path = _apply_redactions(str(run_log_path), redactions)
    commands: list[PipelineCommand] = []
    notices: list[str] = []
    execution_backend = str(config.execution_backend or 'local').strip().lower()
    preflight: dict[str, str | bool] = {'available': True, 'user_message': 'Local backend active.'}

    if execution_backend == 'docker':
        preflight = docker_preflight()
        if not preflight.get('available'):
            raise ValueError(str(preflight.get('user_message', 'Docker is unavailable.')))
        if config.vendor_mode and config.vendor_mode != 'static':
            raise ValueError('Docker backend requires vendor_mode=static so stamped apps do not depend on host library paths.')
        sandbox_root = config.resolved_sandbox_root()
        if not _is_relative_to(sandbox_root, HOST_SANDBOX_APPS_ROOT):
            raise ValueError(f'Docker backend requires sandbox_root under {HOST_SANDBOX_APPS_ROOT}.')
        if config.promote_after and not _is_relative_to(promote_destination, HOST_SANDBOX_ROOT) and not config.allow_host_writes:
            raise ValueError('Promotion outside _sandbox requires explicit host-write approval. Enable approval in the runner UI before building the queue.')
        container_plan = _build_docker_commands(config, workspace_root, patch_paths, redactions)
        commands.extend(container_plan['commands'])
        notices.extend(container_plan['notices'])
        if config.promote_after:
            commands.append(_make_local_command(
                label='Promote validated app' + (' (host-approved)' if not _is_relative_to(promote_destination, HOST_SANDBOX_ROOT) else ''),
                args=[
                    config.python_executable,
                    '-m',
                    'library.app_factory',
                    'sandbox-promote',
                    str(workspace_root),
                    '--destination',
                    str(promote_destination),
                    *(['--force'] if config.promote_force else []),
                ],
                cwd=str(HOST_REPO_ROOT),
                redactions=redactions,
            ))
        if not _is_relative_to(promote_destination, HOST_SANDBOX_ROOT):
            notices.append('Host promotion is queued as a separate approved step because the destination is outside _sandbox.')
    else:
        commands.extend(_build_local_commands(config, workspace_root, patch_paths, promote_destination, redactions))
        if not _is_relative_to(promote_destination, HOST_SANDBOX_ROOT) and config.promote_after:
            notices.append('Host promotion target is outside _sandbox. Terminal output is redacted, but files will be written to the approved host destination.')

    return {
        'workspace_root': str(workspace_root),
        'display_workspace_root': display_workspace_root,
        'promote_destination': str(promote_destination),
        'display_promote_destination': display_promote_destination,
        'run_log_path': str(run_log_path),
        'display_run_log_path': display_run_log_path,
        'execution_backend': execution_backend,
        'preflight': preflight,
        'notices': notices,
        'commands': commands,
        'display_commands': [command.prompt_line() for command in commands],
        'redactions': redactions,
    }


def _build_local_commands(
    config: SandboxRunConfig,
    workspace_root: Path,
    patch_paths: list[Path],
    promote_destination: Path,
    redactions: list[tuple[str, str]],
) -> list[PipelineCommand]:
    commands: list[PipelineCommand] = []
    stamp_args = [
        config.python_executable,
        '-m',
        'library.app_factory',
        'sandbox-stamp',
        '--run-id',
        config.run_id,
    ]
    if config.template_id:
        stamp_args.extend(['--template-id', config.template_id])
    if config.manifest_path:
        stamp_args.extend(['--manifest', str(Path(config.manifest_path).resolve())])
    if config.sandbox_root:
        stamp_args.extend(['--sandbox-root', str(config.resolved_sandbox_root())])
    if config.name:
        stamp_args.extend(['--name', config.name])
    if config.vendor_mode:
        stamp_args.extend(['--vendor-mode', config.vendor_mode])
    if config.resolution_profile:
        stamp_args.extend(['--resolution-profile', config.resolution_profile])
    if config.force_stamp:
        stamp_args.append('--force')
    commands.append(_make_local_command('Stamp sandbox workspace', stamp_args, str(HOST_REPO_ROOT), redactions))

    if patch_paths:
        apply_args = [
            config.python_executable,
            '-m',
            'library.app_factory',
            'sandbox-apply',
            str(workspace_root),
            *[str(path) for path in patch_paths],
        ]
        if not config.backup_patches:
            apply_args.append('--no-backup')
        commands.append(_make_local_command('Apply patch manifests', apply_args, str(HOST_REPO_ROOT), redactions))

    validate_args = [
        config.python_executable,
        '-m',
        'library.app_factory',
        'sandbox-validate',
        str(workspace_root),
    ]
    commands.append(_make_local_command('Validate transformed app', validate_args, str(HOST_REPO_ROOT), redactions))

    if config.promote_after:
        promote_args = [
            config.python_executable,
            '-m',
            'library.app_factory',
            'sandbox-promote',
            str(workspace_root),
            '--destination',
            str(promote_destination),
        ]
        if config.promote_force:
            promote_args.append('--force')
        commands.append(_make_local_command('Promote validated app', promote_args, str(HOST_REPO_ROOT), redactions))
    return commands


def _build_docker_commands(
    config: SandboxRunConfig,
    workspace_root: Path,
    patch_paths: list[Path],
    redactions: list[tuple[str, str]],
) -> dict:
    docker_binary = str(docker_preflight().get('binary_path') or DEFAULT_DOCKER_EXECUTABLE)
    mounts: list[tuple[Path, PurePosixPath, bool]] = []
    _add_mount(mounts, HOST_REPO_ROOT, CONTAINER_REPO_ROOT, readonly=True)
    _add_mount(mounts, HOST_SANDBOX_ROOT, CONTAINER_WORKSPACE_ROOT, readonly=False)
    notices = [
        'Docker backend uses a read-only repo mount at /repo and a writable sandbox mount at /workspace.',
        'Docker runs force static vendoring and build the catalog under /workspace/catalog/catalog.db.',
    ]
    container_manifest_path = ''
    if config.manifest_path:
        container_manifest_path = _container_path_for_host(Path(config.manifest_path).resolve(), mounts, 'manifest', 0)
    container_patch_paths = [
        _container_path_for_host(path, mounts, 'patch', index)
        for index, path in enumerate(patch_paths)
    ]
    container_workspace_root = CONTAINER_SANDBOX_APPS_ROOT / config.run_id
    container_sandbox_root = CONTAINER_SANDBOX_APPS_ROOT

    stamp_args = [
        'python',
        '-m',
        'library.app_factory',
        'sandbox-stamp',
        '--run-id',
        config.run_id,
        '--sandbox-root',
        str(container_sandbox_root),
        '--vendor-mode',
        'static',
    ]
    if config.template_id:
        stamp_args.extend(['--template-id', config.template_id])
    if container_manifest_path:
        stamp_args.extend(['--manifest', container_manifest_path])
    if config.name:
        stamp_args.extend(['--name', config.name])
    if config.resolution_profile:
        stamp_args.extend(['--resolution-profile', config.resolution_profile])
    if config.force_stamp:
        stamp_args.append('--force')

    commands = [
        _make_docker_command(
            docker_binary,
            config.docker_image,
            mounts,
            'Stamp sandbox workspace (docker)',
            stamp_args,
            redactions,
        )
    ]

    if container_patch_paths:
        apply_args = [
            'python',
            '-m',
            'library.app_factory',
            'sandbox-apply',
            str(container_workspace_root),
            *container_patch_paths,
        ]
        if not config.backup_patches:
            apply_args.append('--no-backup')
        commands.append(_make_docker_command(
            docker_binary,
            config.docker_image,
            mounts,
            'Apply patch manifests (docker)',
            apply_args,
            redactions,
        ))

    validate_args = [
        'python',
        '-m',
        'library.app_factory',
        'sandbox-validate',
        str(container_workspace_root),
    ]
    commands.append(_make_docker_command(
        docker_binary,
        config.docker_image,
        mounts,
        'Validate transformed app (docker)',
        validate_args,
        redactions,
    ))
    return {'commands': commands, 'notices': notices}

def _make_local_command(label: str, args: list[str], cwd: str, redactions: list[tuple[str, str]]) -> PipelineCommand:
    display_cwd = _apply_redactions(cwd, redactions)
    display_command = _apply_redactions(subprocess.list2cmdline([str(part) for part in args]), redactions)
    return PipelineCommand(label=label, args=args, cwd=cwd, display_cwd=display_cwd, display_command=display_command, redactions=redactions)


def _make_docker_command(
    docker_binary: str,
    docker_image: str,
    mounts: list[tuple[Path, PurePosixPath, bool]],
    label: str,
    inner_args: list[str],
    redactions: list[tuple[str, str]],
) -> PipelineCommand:
    command = [docker_binary, 'run', '--rm', '--network', 'none', '--workdir', str(CONTAINER_REPO_ROOT)]
    for source, target, readonly in mounts:
        mount_spec = f'type=bind,source={source},target={target}' + (',readonly' if readonly else '')
        command.extend(['--mount', mount_spec])
    command.extend([
        '--env', f'PYTHONPATH={CONTAINER_REPO_ROOT}',
        '--env', f'APP_FOUNDRY_CATALOG_DB_PATH={CONTAINER_CATALOG_DB_PATH}',
        docker_image,
        *inner_args,
    ])
    display_command = '[docker] ' + ' '.join(str(part) for part in inner_args)
    return PipelineCommand(
        label=label,
        args=command,
        cwd=str(HOST_REPO_ROOT),
        display_cwd=str(CONTAINER_REPO_ROOT),
        display_command=display_command,
        redactions=redactions,
    )


def _add_mount(mounts: list[tuple[Path, PurePosixPath, bool]], source: Path, target: PurePosixPath, *, readonly: bool) -> None:
    item = (source.resolve(), target, readonly)
    if item not in mounts:
        mounts.append(item)


def _container_path_for_host(host_path: Path, mounts: list[tuple[Path, PurePosixPath, bool]], label: str, index: int) -> str:
    host_path = host_path.resolve()
    if _is_relative_to(host_path, HOST_REPO_ROOT):
        return str(CONTAINER_REPO_ROOT / PurePosixPath(host_path.relative_to(HOST_REPO_ROOT).as_posix()))
    if _is_relative_to(host_path, HOST_SANDBOX_ROOT):
        return str(CONTAINER_WORKSPACE_ROOT / PurePosixPath(host_path.relative_to(HOST_SANDBOX_ROOT).as_posix()))
    target_root = PurePosixPath('/inputs') / f'{label}{index}'
    _add_mount(mounts, host_path.parent, target_root, readonly=True)
    return str(target_root / host_path.name)


def _build_redactions(config: SandboxRunConfig, workspace_root: Path, promote_destination: Path) -> list[tuple[str, str]]:
    mappings: list[tuple[str, str]] = []
    mappings.append((str(HOST_REPO_ROOT), '/repo'))
    mappings.append((str(HOST_SANDBOX_ROOT), '/workspace'))
    mappings.append((str(LEGACY_SANDBOX_ROOT), '/workspace'))
    mappings.append((str(HOST_SANDBOX_APPS_ROOT), '/workspace/apps'))
    mappings.append((str(LEGACY_SANDBOX_ROOT / 'apps'), '/workspace/apps'))
    mappings.append((str(workspace_root), f'/workspace/apps/{config.run_id}'))
    if _is_relative_to(promote_destination, HOST_SANDBOX_ROOT):
        relative = promote_destination.relative_to(HOST_SANDBOX_ROOT).as_posix()
        mappings.append((str(promote_destination), f'/workspace/{relative}'))
    else:
        mappings.append((str(promote_destination), f'/host-approved/{promote_destination.name}'))
    if config.manifest_path:
        manifest_path = Path(config.manifest_path).resolve()
        mappings.append((str(manifest_path), _logical_input_path('manifest', 0, manifest_path.name)))
        mappings.append((str(manifest_path.parent), '/inputs/manifest0'))
    for index, patch_path in enumerate(config.resolved_patch_manifests()):
        mappings.append((str(patch_path), _logical_input_path('patch', index, patch_path.name)))
        mappings.append((str(patch_path.parent), f'/inputs/patch{index}'))
    deduped = {(src, dst) for src, dst in mappings if src and dst}
    return sorted(deduped, key=lambda item: len(item[0]), reverse=True)


def _logical_input_path(label: str, index: int, name: str) -> str:
    return f'/inputs/{label}{index}/{name}'


def _apply_redactions(text: str, redactions: list[tuple[str, str]]) -> str:
    value = str(text)
    for source, target in redactions:
        value = value.replace(source, target)
    return value


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def execute_command_queue(
    commands: Iterable[PipelineCommand],
    *,
    on_event: Optional[Callable[[dict], None]] = None,
    stop_event: Optional[Event] = None,
    typing_delay: float = 0.01,
    run_log_path: str | Path | None = None,
    display_run_log_path: str = '',
) -> dict:
    command_list = list(commands)
    run_log = Path(run_log_path).resolve() if run_log_path else None
    run_log_redactions = command_list[0].redactions if command_list else []
    if run_log is not None:
        run_log.parent.mkdir(parents=True, exist_ok=True)

    def emit(event: dict) -> None:
        payload = {'timestamp': datetime.now().isoformat(timespec='seconds'), **event}
        if run_log is not None:
            with run_log.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(payload, ensure_ascii=True) + '\n')
        if on_event is not None:
            on_event(payload)

    emit({
        'type': 'run_started',
        'step_count': len(command_list),
        'run_log_path': display_run_log_path or (_apply_redactions(str(run_log), run_log_redactions) if run_log else ''),
    })
    completed = 0
    for index, command in enumerate(command_list, start=1):
        if stop_event is not None and stop_event.is_set():
            emit({'type': 'run_aborted', 'completed_steps': completed})
            return {'ok': False, 'aborted': True, 'completed_steps': completed, 'run_log_path': str(run_log) if run_log else ''}
        emit({'type': 'step_started', 'step_index': index, 'label': command.label, 'command': command.render_display()})
        command_line = command.prompt_line() + '\n'
        for char in command_line:
            if stop_event is not None and stop_event.is_set():
                emit({'type': 'run_aborted', 'completed_steps': completed})
                return {'ok': False, 'aborted': True, 'completed_steps': completed, 'run_log_path': str(run_log) if run_log else ''}
            emit({'type': 'command_char', 'text': char, 'step_index': index})
            if typing_delay > 0:
                time.sleep(typing_delay)
        process = subprocess.Popen(
            command.args,
            cwd=command.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        aborted = False
        try:
            assert process.stdout is not None
            for line in process.stdout:
                emit({'type': 'stdout', 'text': command.redact(line), 'step_index': index})
                if stop_event is not None and stop_event.is_set():
                    aborted = True
                    process.terminate()
                    break
        finally:
            returncode = process.wait()
        if aborted:
            emit({'type': 'run_aborted', 'completed_steps': completed, 'returncode': returncode})
            return {'ok': False, 'aborted': True, 'completed_steps': completed, 'run_log_path': str(run_log) if run_log else ''}
        emit({'type': 'step_finished', 'step_index': index, 'label': command.label, 'returncode': returncode})
        if returncode != 0:
            emit({'type': 'run_finished', 'ok': False, 'failed_step': index, 'returncode': returncode})
            return {
                'ok': False,
                'aborted': False,
                'failed_step': index,
                'returncode': returncode,
                'completed_steps': completed,
                'run_log_path': str(run_log) if run_log else '',
            }
        completed = index
    emit({'type': 'run_finished', 'ok': True, 'completed_steps': completed})
    return {'ok': True, 'aborted': False, 'completed_steps': completed, 'run_log_path': str(run_log) if run_log else ''}
