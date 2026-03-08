"""
inject_register_hook.py
Walks a directory of microservice files and injects the register() method
into any class decorated with @service_metadata that doesn't already have it.

Usage:
    python inject_register_hook.py ./microservices
    python inject_register_hook.py ./microservices --dry-run
"""

import argparse
import ast
import re
import sys
from pathlib import Path

REGISTER_METHOD = '''
    def register(self, registry, group=None):
        """Auto-injected registration hook. Latches onto @service_metadata fields."""
        meta = getattr(self, '_service_info', None) or getattr(self, '_meta', {})
        registry.register(
            name=meta.get('name', self.__class__.__name__),
            version=meta.get('version', '0.0.0'),
            tags=meta.get('tags', []),
            capabilities=meta.get('capabilities', []),
            instance=self,
            group=group,
        )
'''


def has_service_metadata(source: str) -> bool:
    return '@service_metadata' in source


def has_register_method(source: str) -> bool:
    return 'def register(self' in source


def find_get_health_position(source: str) -> int:
    """
    Find the line index of 'def get_health' inside the class.
    We insert register() immediately before get_health() so it stays
    grouped with the standard interface methods.
    """
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if re.match(r'\s+def get_health\(self', line):
            return i
    return -1


def inject(source: str) -> str:
    pos = find_get_health_position(source)
    if pos == -1:
        # Fallback: append before last line of file
        lines = source.splitlines()
        pos = len(lines) - 1

    lines = source.splitlines()
    # Insert register() block before get_health
    register_lines = REGISTER_METHOD.splitlines()
    lines = lines[:pos] + register_lines + [''] + lines[pos:]
    return '\n'.join(lines)


def process_file(path: Path, dry_run: bool) -> str:
    source = path.read_text(encoding='utf-8')

    if not has_service_metadata(source):
        return 'skip:no_metadata'

    if has_register_method(source):
        return 'skip:already_has_register'

    injected = inject(source)

    if dry_run:
        print(f'\n--- DRY RUN: {path.name} ---')
        # Show the 10 lines around the injection point
        lines = injected.splitlines()
        pos = find_get_health_position(injected)
        start = max(0, pos - 2)
        end = min(len(lines), pos + 14)
        for i, line in enumerate(lines[start:end], start=start):
            print(f'{i:4}: {line}')
        return 'dry_run:would_inject'

    path.write_text(injected, encoding='utf-8')
    return 'injected'


def main():
    parser = argparse.ArgumentParser(description='Inject register() hook into microservice files.')
    parser.add_argument('directory', help='Directory containing microservice .py files')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing')
    parser.add_argument('--pattern', default='*.py', help='File glob pattern (default: *.py)')
    args = parser.parse_args()

    target = Path(args.directory)
    if not target.exists():
        print(f'Error: {target} does not exist.')
        sys.exit(1)

    files = sorted(target.glob(args.pattern))
    if not files:
        print(f'No files matching {args.pattern} in {target}')
        sys.exit(0)

    results = {'injected': [], 'skip:already_has_register': [], 'skip:no_metadata': [], 'dry_run:would_inject': [], 'error': []}

    for f in files:
        try:
            result = process_file(f, dry_run=args.dry_run)
            results[result].append(f.name)
            status = result.upper()
            print(f'  {status:<30} {f.name}')
        except Exception as e:
            results['error'].append(f.name)
            print(f'  ERROR                          {f.name}: {e}')

    print('\n--- Summary ---')
    print(f"  Injected:          {len(results['injected'])}")
    print(f"  Already had hook:  {len(results['skip:already_has_register'])}")
    print(f"  No metadata:       {len(results['skip:no_metadata'])}")
    if args.dry_run:
        print(f"  Would inject:      {len(results['dry_run:would_inject'])}")
    print(f"  Errors:            {len(results['error'])}")


if __name__ == '__main__':
    main()
