#!/usr/bin/env python3
"""Build the pinned core from source. Network access is confined to build inputs."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def run(*args, cwd=ROOT, **kwargs):
    return subprocess.run(args, cwd=cwd, check=True, **kwargs)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, help='Existing clone of the pinned public core source')
    options = parser.parse_args()
    lock_bytes = (ROOT / 'core/source.lock.json').read_bytes()
    lock = json.loads(lock_bytes)
    patch_hash = hashlib.sha256()
    patches = []
    for name in lock['patches']:
        if Path(name).name != name:
            raise ValueError('Patch names must be plain filenames')
        path = ROOT / 'core/patches' / name
        patch_hash.update(name.encode() + b'\0' + path.read_bytes())
        patches.append(path)
    patch_digest = patch_hash.hexdigest()
    build_root = ROOT / '.build'
    build_root.mkdir(exist_ok=True)
    source = options.source.resolve() if options.source else build_root / 'core-source'
    if not source.exists():
        run('git', '-c', 'core.hooksPath=/dev/null', 'clone', '--no-checkout', '--filter=blob:none', lock['repository'], str(source))
    commit = run('git', 'rev-parse', lock['commit'] + '^{commit}', cwd=source, capture_output=True, text=True).stdout.strip()
    if commit != lock['commit']:
        raise ValueError('Core source does not match the pinned commit')
    goos = {'Darwin': 'darwin', 'Linux': 'linux', 'Windows': 'windows'}[platform.system()]
    goarch = {'arm64': 'arm64', 'aarch64': 'arm64', 'AMD64': 'amd64', 'x86_64': 'amd64'}[platform.machine()]
    artifact_arch = 'aarch64' if goarch == 'arm64' else 'amd64'
    binary_name = 'cli-proxy-api.exe' if goos == 'windows' else 'cli-proxy-api'
    output = build_root / 'private-core-artifacts'
    output.mkdir(exist_ok=True)
    binary = output / binary_name
    source_tar = run('git', 'archive', commit, cwd=source, capture_output=True).stdout
    env = dict(os.environ, CGO_ENABLED='0', GOTOOLCHAIN='local', GOTELEMETRY='off',
               GOCACHE=str(build_root / 'go-cache'), GOMODCACHE=str(build_root / 'go-mod'))
    with tempfile.TemporaryDirectory(prefix='core-build-', dir=build_root) as work:
        work = Path(work)
        with tarfile.open(fileobj=io.BytesIO(source_tar)) as archive:
            archive.extractall(work, filter='data')
        run('git', 'init', '-q', str(work))
        for patch in patches:
            run('git', 'apply', '--check', str(patch), cwd=work)
            run('git', 'apply', str(patch), cwd=work)
        run('go', 'test', '-mod=readonly', '-count=1', '-run', 'TestPrivateBuild',
            './internal/privatebuild', './internal/registry', './internal/managementasset',
            './internal/misc', './internal/runtime/executor/helps', './internal/store',
            './internal/util', './internal/pluginhost', './sdk/cliproxy',
            './internal/api/handlers/management', './sdk/auth', cwd=work, env=env)
        flags = f"-s -w -X main.Version={lock['version']}-private -X main.Commit={commit}-private.{patch_digest[:12]}"
        run('go', 'build', '-mod=readonly', '-trimpath', '-buildvcs=false', '-ldflags', flags,
            '-o', str(binary), './cmd/server', cwd=work, env=env)
        if goos == 'darwin':
            run('codesign', '--force', '--sign', '-', '--timestamp=none', str(binary))
            run('codesign', '--verify', '--strict', str(binary))
        binary_bytes = binary.read_bytes()
        members = {
            binary_name: (binary_bytes, 0o755),
            'config.example.yaml': ((work / 'config.example.yaml').read_bytes(), 0o600),
            'LICENSE': ((work / 'LICENSE').read_bytes(), 0o644),
        }
        suffix = 'zip' if goos == 'windows' else 'tar.gz'
        asset = f"CLIProxyAPI_{lock['version']}_{goos}_{artifact_arch}.{suffix}"
        core_dir = ROOT / 'cpa-core'
        core_dir.mkdir(exist_ok=True)
        archive_path = core_dir / asset
        if suffix == 'zip':
            with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, (data, mode) in members.items():
                    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    entry.external_attr = (0o100000 | mode) << 16
                    archive.writestr(entry, data)
        else:
            with archive_path.open('wb') as dest, gzip.GzipFile(filename='', mode='wb', fileobj=dest, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode='w') as archive:
                    for name, (data, mode) in members.items():
                        entry = tarfile.TarInfo(name)
                        entry.size, entry.mode, entry.mtime = len(data), mode, 0
                        archive.addfile(entry, io.BytesIO(data))
    archive_digest = sha(archive_path.read_bytes())
    manifest = dict(schema=1, sourceCommit=commit, lockSha256=sha(lock_bytes), patchSetSha256=patch_digest,
                    privacyRevision=lock['privacyRevision'], platform=goos, arch=goarch,
                    binary=str(binary.relative_to(ROOT)), binarySha256=sha(binary_bytes),
                    archive=str(archive_path.relative_to(ROOT)), archiveSha256=archive_digest)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (core_dir / 'checksums.txt').write_text(f'{archive_digest}  {asset}\n')
    print('Private core manifest:', output / 'manifest.json')


if __name__ == '__main__':
    main()
