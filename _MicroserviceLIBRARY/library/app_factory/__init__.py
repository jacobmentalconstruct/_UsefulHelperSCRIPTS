"""Static-analysis catalog, librarian, and app-stamping helpers."""

from .assistant import OllamaAssistantService
from .catalog import CatalogBuilder
from .librarian_ui import LibrarianApp
from .models import AppBlueprintManifest, StamperValidationResult
from .packs import InstallPackManager
from .pipeline_runner import PipelineCommand, SandboxRunConfig, build_sandbox_command_queue, execute_command_queue
from .query import LibraryQueryService
from .sandbox import SandboxWorkflow
from .stamper import AppStamper
from .ui_schema import UiSchemaCommitService, UiSchemaPreviewService

__all__ = [
    "AppBlueprintManifest",
    "AppStamper",
    "CatalogBuilder",
    "InstallPackManager",
    "LibraryQueryService",
    "LibrarianApp",
    "OllamaAssistantService",
    "PipelineCommand",
    "PipelineRunnerApp",
    "SandboxRunConfig",
    "SandboxWorkflow",
    "StamperValidationResult",
    "UiSchemaCommitService",
    "UiSchemaPreviewService",
    "build_sandbox_command_queue",
    "execute_command_queue",
]

def __getattr__(name):
    if name == "PipelineRunnerApp":
        from .runner_ui import PipelineRunnerApp
        return PipelineRunnerApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
