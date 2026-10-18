#!/usr/bin/env python3
"""Apply the pinned WE network series to a synchronized Wine build tree only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

PROTON_BASE = '4b3d2918bd8d6880451f012bf2ced4e337447083'
WINE_BASE = '6a7adb2adf750046ad01091b369ea95c8b551a30'
WE_BASE = '8cfdd8c45c6d6c2d92ecd8f118fb03e0a28b08a7'
ORDER = ('0015', '0016', '0017', '0048', '0053')
ROOT = Path(__file__).resolve().parents[2]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f'{args[0]} failed: {result.stderr.strip()}')
    return result.stdout.strip()


def safe_path(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(f'Unsafe path: {relative}')
    target = root / path
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f'Symlink not permitted: {relative}')
    if target.exists() and not target.is_file():
        raise ValueError(f'Not a regular file: {relative}')
    return target


def apply(source, bundle=ROOT / 'patches/wine-tun', check=False, origin=None):
    source, bundle = Path(source).resolve(), Path(bundle).resolve()
    if not source.is_dir():
        raise ValueError(f'Wine source directory missing: {source}')
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if (manifest['proton_base'], manifest['wine_base'], manifest['we_base']) != (PROTON_BASE, WINE_BASE, WE_BASE):
        raise ValueError('Pinned baseline identity mismatch')
    rows = manifest['patches']
    if tuple(row['name'][:4] for row in rows) != ORDER:
        raise ValueError('Patch order/count mismatch')
    expected = {row['name'] for row in rows}
    if {p.name for p in bundle.glob('*.patch')} != expected:
        raise ValueError('Patch inventory mismatch')
    if origin is not None:
        origin = Path(origin).resolve()
        if origin == source:
            raise ValueError('Refusing to patch original Wine submodule; use synchronized build source')
        if run(['git', 'rev-parse', 'HEAD'], origin) != WINE_BASE:
            raise ValueError('Wine submodule HEAD does not match pinned baseline')
        if run(['git', 'ls-tree', 'HEAD', 'wine'], ROOT).split()[:3] != ['160000', 'commit', WINE_BASE]:
            raise ValueError('Proton Wine gitlink differs from manifest')
    patches = []
    paths = set()
    for row in rows:
        patch = safe_path(bundle, row['name']).read_bytes()
        if digest(patch) != row['sha256']:
            raise ValueError(f'Patch hash mismatch: {row["name"]}')
        for old, new in re.findall(rb'^diff --git a/(\S+) b/(\S+)$', patch, re.M):
            if old != new:
                raise ValueError('Renames are not supported by this series')
            paths.add(old.decode())
        patches.append((row['name'], patch))
    files = manifest['files']
    if not paths or paths != set(files):
        raise ValueError('Touched-file inventory mismatch')
    observed = {}
    for name in sorted(paths):
        target = safe_path(source, name)
        observed[name] = digest(target.read_bytes()) if target.exists() else None
    if all(observed[name] == files[name]['patched_sha256'] for name in paths):
        return 'already-applied'
    if not all(observed[name] == files[name]['base_sha256'] for name in paths):
        raise ValueError('Source content differs from pinned baseline (mixed, partial or unknown state); resync clean source')
    # Preflight the COMPLETE ordered series on a private copy before any source writes.
    with tempfile.TemporaryDirectory(prefix='cachyos-tun-') as temp:
        temp = Path(temp)
        tree = temp / 'wine'
        tree.mkdir()
        for name in paths:
            target = safe_path(source, name)
            if target.exists():
                destination = tree / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, destination)
        for index, (name, patch) in enumerate(patches):
            patchfile = temp / f'{index}.patch'
            patchfile.write_bytes(patch)
            run(['git', 'apply', '--no-index', '--check', str(patchfile)], tree)
            run(['git', 'apply', '--no-index', str(patchfile)], tree)
        for name in paths:
            target = safe_path(tree, name)
            actual = digest(target.read_bytes()) if target.exists() else None
            if actual != files[name]['patched_sha256']:
                raise ValueError(f'Patched output hash mismatch: {name}')
        if check:
            return 'check-passed'
        for name in sorted(paths):
            target = safe_path(source, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tree / name, target)
    return 'applied'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'patches/wine-tun')
    parser.add_argument('--origin', type=Path, help='Also verify original Wine HEAD and Proton gitlink; never modify origin')
    parser.add_argument('--check', action='store_true', help='Preflight only; do not modify source')
    args = parser.parse_args()
    try:
        print('TUN series:', apply(args.source, args.bundle, args.check, args.origin))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f'TUN series refused: {error}\n')


if __name__ == '__main__':
    main()
