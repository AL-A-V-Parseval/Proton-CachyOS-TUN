#!/usr/bin/env python3
"""Verify fixed upstream file bytes and the full patch series; NOT a Wine build."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
from urllib.request import urlopen

import apply as tun


def main():
    bundle = tun.ROOT / 'patches/wine-tun'
    manifest = json.loads((bundle / 'manifest.json').read_text())
    with tempfile.TemporaryDirectory(prefix='tun-verify-') as temp:
        source = Path(temp) / 'wine'
        source.mkdir()

        def fetch(item):
            name, values = item
            if values['base_sha256'] is None:
                return
            url = f'https://raw.githubusercontent.com/CachyOS/wine-cachyos/{tun.WINE_BASE}/{name}'
            with urlopen(url, timeout=60) as response:
                data = response.read()
            if tun.digest(data) != values['base_sha256']:
                raise ValueError(f'Upstream fingerprint mismatch: {name}')
            destination = tun.safe_path(source, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(fetch, manifest['files'].items()))
        assert tun.apply(source, check=True) == 'check-passed'
        assert tun.apply(source) == 'applied'
        assert tun.apply(source) == 'already-applied'
        assert tun.apply(source, check=True) == 'already-applied'
        print(f'PASS: {len(manifest["patches"])} patches, {len(manifest["files"])} touched paths; preflight/application/idempotence')
        print('Scope: fixed touched-file snapshot only; no full checkout, compile, packaging or runtime proof.')


if __name__ == '__main__':
    main()
