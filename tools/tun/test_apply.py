"""Behavioral tests for apply.py using a synthetic, isolated patch bundle."""

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name('apply.py')
SPEC = importlib.util.spec_from_file_location('tun_apply', SCRIPT)
tun_apply = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tun_apply)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_text(path, before, after):
    """Return a minimal git-apply-compatible one-line patch."""
    return (
        f'diff --git a/{path} b/{path}\n'
        f'--- a/{path}\n'
        f'+++ b/{path}\n'
        '@@ -1 +1 @@\n'
        f'-{before.decode()}\n'
        f'+{after.decode()}\n'
    ).encode()


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tun-apply-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'wine-build-source'
        self.bundle = self.root / 'bundle'
        self.source.mkdir()
        self.bundle.mkdir()
        self.manifest_path = self.bundle / 'manifest.json'
        self.rows = []
        self.file_rows = {}
        self.patches = {}
        for index, number in enumerate(tun_apply.ORDER):
            name = f'{number}-synthetic.patch'
            path = f'dlls/test{index}/source.c'
            before = f'base-{index}\n'.encode()
            after = f'patched-{index}\n'.encode()
            target = self.source / path
            target.parent.mkdir(parents=True)
            target.write_bytes(before)
            data = patch_text(path, before.rstrip(b'\n'), after.rstrip(b'\n'))
            self.patches[name] = data
            self.rows.append({'name': name, 'sha256': sha(data)})
            self.file_rows[path] = {
                'base_sha256': sha(before),
                'patched_sha256': sha(after),
            }
        self.write_bundle()

    def write_bundle(self, rows=None, files=None):
        rows = self.rows if rows is None else rows
        files = self.file_rows if files is None else files
        for name, data in self.patches.items():
            (self.bundle / name).write_bytes(data)
        manifest = {
            'proton_base': tun_apply.PROTON_BASE,
            'wine_base': tun_apply.WINE_BASE,
            'we_base': tun_apply.WE_BASE,
            'patches': rows,
            'files': files,
        }
        self.manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

    def read_manifest(self):
        return json.loads(self.manifest_path.read_text(encoding='utf-8'))

    def source_snapshot(self):
        return {
            p.relative_to(self.source).as_posix(): p.read_bytes()
            for p in self.source.rglob('*') if p.is_file() and not p.is_symlink()
        }

    def test_check_preflights_complete_series_without_writing_source(self):
        before = self.source_snapshot()
        before_entries = sorted(p.relative_to(self.source).as_posix() for p in self.source.rglob('*'))
        self.assertEqual(tun_apply.apply(self.source, self.bundle, check=True), 'check-passed')
        self.assertEqual(self.source_snapshot(), before)
        self.assertEqual(
            sorted(p.relative_to(self.source).as_posix() for p in self.source.rglob('*')),
            before_entries,
        )

    def test_apply_writes_expected_outputs(self):
        self.assertEqual(tun_apply.apply(self.source, self.bundle), 'applied')
        for path, row in self.file_rows.items():
            self.assertEqual(sha((self.source / path).read_bytes()), row['patched_sha256'])

    def test_already_applied_series_is_idempotent(self):
        self.assertEqual(tun_apply.apply(self.source, self.bundle), 'applied')
        after_first_apply = self.source_snapshot()
        self.assertEqual(tun_apply.apply(self.source, self.bundle), 'already-applied')
        self.assertEqual(self.source_snapshot(), after_first_apply)

    def test_patch_order_and_count_are_pinned(self):
        reordered = list(self.rows)
        reordered[0], reordered[1] = reordered[1], reordered[0]
        self.write_bundle(rows=reordered)
        with self.assertRaisesRegex(ValueError, 'order/count'):
            tun_apply.apply(self.source, self.bundle)

        self.write_bundle(rows=self.rows[:-1])
        with self.assertRaisesRegex(ValueError, 'order/count'):
            tun_apply.apply(self.source, self.bundle)

    def test_patch_inventory_must_match_manifest(self):
        (self.bundle / self.rows[-1]['name']).unlink()
        before = self.source_snapshot()
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            tun_apply.apply(self.source, self.bundle)
        self.assertEqual(self.source_snapshot(), before)

    def test_patch_hash_mismatch_fails_before_source_write(self):
        name = self.rows[2]['name']
        (self.bundle / name).write_bytes(self.patches[name] + b'# tampered\n')
        before = self.source_snapshot()
        with self.assertRaisesRegex(ValueError, 'Patch hash mismatch'):
            tun_apply.apply(self.source, self.bundle)
        self.assertEqual(self.source_snapshot(), before)

    def test_pinned_source_content_mismatch_fails(self):
        path = next(iter(self.file_rows))
        (self.source / path).write_bytes(b'unexpected source\n')
        before = self.source_snapshot()
        with self.assertRaisesRegex(ValueError, 'Source content differs'):
            tun_apply.apply(self.source, self.bundle)
        self.assertEqual(self.source_snapshot(), before)

    def test_partial_or_mixed_application_fails_closed(self):
        path = next(iter(self.file_rows))
        (self.source / path).write_bytes(f'patched-0\n'.encode())
        before = self.source_snapshot()
        with self.assertRaisesRegex(ValueError, 'mixed, partial or unknown state'):
            tun_apply.apply(self.source, self.bundle)
        self.assertEqual(self.source_snapshot(), before)

    def test_late_patch_failure_does_not_partially_write_source(self):
        name = self.rows[-1]['name']
        path = f'dlls/test{len(self.rows) - 1}/source.c'
        bad = patch_text(path, b'not-the-base-line', b'wrong-output')
        self.patches[name] = bad
        rows = [dict(row) for row in self.rows]
        rows[-1]['sha256'] = sha(bad)
        self.write_bundle(rows=rows)
        before = self.source_snapshot()

        with self.assertRaises(ValueError):
            tun_apply.apply(self.source, self.bundle)
        self.assertEqual(self.source_snapshot(), before)

    def test_origin_with_wrong_wine_head_is_rejected(self):
        origin = self.root / 'wine-origin'
        origin.mkdir()
        subprocess.run(['git', 'init', '-q', str(origin)], check=True)
        subprocess.run(['git', '-C', str(origin), 'config', 'user.name', 'Test'], check=True)
        subprocess.run(['git', '-C', str(origin), 'config', 'user.email', 'test@example.invalid'], check=True)
        (origin / 'README').write_text('fixture\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(origin), 'add', 'README'], check=True)
        subprocess.run(['git', '-C', str(origin), 'commit', '-qm', 'synthetic origin'], check=True)
        before = self.source_snapshot()

        with self.assertRaisesRegex(ValueError, 'Wine submodule HEAD'):
            tun_apply.apply(self.source, self.bundle, origin=origin)
        self.assertEqual(self.source_snapshot(), before)

    def test_symlinked_touched_file_is_rejected(self):
        path = next(iter(self.file_rows))
        target = self.source / path
        real = self.root / 'outside.c'
        real.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(real)
        before = real.read_bytes()

        with self.assertRaisesRegex(ValueError, 'Symlink not permitted'):
            tun_apply.apply(self.source, self.bundle, check=True)
        self.assertEqual(real.read_bytes(), before)

    def test_patched_output_hash_mismatch_does_not_write_source(self):
        manifest = self.read_manifest()
        path = next(iter(manifest['files']))
        manifest['files'][path]['patched_sha256'] = '0' * 64
        self.manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        before = self.source_snapshot()
        with self.assertRaisesRegex(ValueError, 'Patched output hash mismatch'):
            tun_apply.apply(self.source, self.bundle)
        self.assertEqual(self.source_snapshot(), before)

    def test_manifest_baseline_mismatch_is_rejected(self):
        manifest = self.read_manifest()
        manifest['wine_base'] = '0' * 40
        self.manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        before = self.source_snapshot()

        with self.assertRaisesRegex(ValueError, 'Pinned baseline identity mismatch'):
            tun_apply.apply(self.source, self.bundle)
        self.assertEqual(self.source_snapshot(), before)


if __name__ == '__main__':
    unittest.main()
