"""Local folder/zip install-pack workflow with conservative collision handling."""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .catalog import CatalogBuilder
from .constants import LIBRARY_ROOT


class InstallPackManager:
    def __init__(self, catalog_builder: Optional[CatalogBuilder]=None, library_root: Path | None=None):
        self.catalog_builder = catalog_builder or CatalogBuilder()
        self.library_root = Path(library_root or LIBRARY_ROOT).resolve()
        self.staging_root = self.library_root / 'catalog' / 'install_staging'
        self.report_root = self.library_root / 'catalog' / 'install_reports'

    def install(self, source: Path | str, collision_policy: str='skip') -> Dict[str, Any]:
        if collision_policy != 'skip':
            raise ValueError('Only skip collision policy is supported in v1.')
        source_path = Path(source).resolve()
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        stage_dir = self.staging_root / f'{source_path.stem}_{stamp}'
        stage_dir.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            unpack_root = stage_dir / source_path.name
            shutil.copytree(source_path, unpack_root, dirs_exist_ok=True)
        else:
            unpack_root = stage_dir / source_path.stem
            unpack_root.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(source_path, 'r') as archive:
                archive.extractall(unpack_root)
        candidate_root = unpack_root / 'library' if (unpack_root / 'library').exists() else unpack_root
        copied: List[str] = []
        duplicates: List[str] = []
        collisions: List[str] = []
        for file_path in candidate_root.rglob('*'):
            if file_path.is_dir() or '__pycache__' in file_path.parts:
                continue
            relative = file_path.relative_to(candidate_root)
            target = self.library_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if self._hash_file(target) == self._hash_file(file_path):
                    duplicates.append(str(target))
                    continue
                collisions.append(str(target))
                continue
            shutil.copy2(file_path, target)
            copied.append(str(target))
        catalog_report = self.catalog_builder.build()
        report = {
            'source': str(source_path),
            'stage_dir': str(stage_dir),
            'copied': copied,
            'duplicates': duplicates,
            'collisions': collisions,
            'collision_policy': collision_policy,
            'catalog_report': catalog_report,
        }
        self.report_root.mkdir(parents=True, exist_ok=True)
        report_path = self.report_root / f'{source_path.stem}_{stamp}.json'
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        report['report_path'] = str(report_path)
        return report

    def _hash_file(self, path: Path) -> str:
        import hashlib
        return hashlib.sha256(path.read_bytes()).hexdigest()
