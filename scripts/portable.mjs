import { createHash } from 'node:crypto';
import { chmod, copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { readAppVersion } from './version.mjs';

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) args.set(process.argv[index], process.argv[index + 1]);
if (args.get('--download') === 'true') throw new Error('Online core downloads are disabled. Build the pinned private core first.');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = resolve(args.get('--output') ?? join(root, 'bin-work'));
const targetOS = args.get('--os') ?? ({ linux: 'linux', darwin: 'darwin', win32: 'windows' })[process.platform];
const targetArch = args.get('--arch') ?? ({ x64: 'amd64', arm64: 'aarch64' })[process.arch];
const binary = resolve(args.get('--binary') ?? join(root, 'src-tauri/target/release', targetOS === 'windows' ? 'cpa-gui.exe' : 'cpa-gui'));
const manifest = JSON.parse(await readFile(join(root, '.build/private-core-artifacts/manifest.json'), 'utf8'));
const digest = (bytes) => createHash('sha256').update(bytes).digest('hex');
const lockBytes = await readFile(join(root, 'core/source.lock.json'));
const lock = JSON.parse(lockBytes);
const patches = createHash('sha256');
for (const name of lock.patches) {
  if (basename(name) !== name) throw new Error('Invalid patch filename');
  patches.update(name).update(Buffer.from([0])).update(await readFile(join(root, 'core/patches', name)));
}
if (manifest.schema !== 1 || manifest.sourceCommit !== lock.commit || manifest.lockSha256 !== digest(lockBytes)
  || manifest.patchSetSha256 !== patches.digest('hex') || manifest.privacyRevision !== lock.privacyRevision
  || manifest.platform !== targetOS || manifest.arch !== (targetArch === 'aarch64' ? 'arm64' : targetArch)) {
  throw new Error('Private core provenance or target changed; rebuild the private core and GUI.');
}
for (const [pathKey, hashKey] of [['binary', 'binarySha256'], ['archive', 'archiveSha256']]) {
  if (digest(await readFile(join(root, manifest[pathKey]))) !== manifest[hashKey]) throw new Error(`Private core ${pathKey} changed; rebuild it.`);
}
const version = (await readFile(join(root, 'core-version.txt'), 'utf8')).trim().replace(/^v/, '');
if (version !== lock.version) throw new Error('core-version.txt must match the pinned private source version');
await mkdir(join(output, 'cpa-core'), { recursive: true });
const outputBinary = join(output, targetOS === 'windows' ? 'EasyCLIProxyAPI.exe' : 'EasyCLIProxyAPI');
await copyFile(binary, outputBinary);
if (targetOS !== 'windows') await chmod(outputBinary, 0o755);
await copyFile(join(root, 'core-version.txt'), join(output, 'core-version.txt'));
await copyFile(join(root, manifest.archive), join(output, 'cpa-core', basename(manifest.archive)));
await writeFile(join(output, 'cpa-core/checksums.txt'), `${manifest.archiveSha256}  ${basename(manifest.archive)}\n`);
await writeFile(join(output, 'private-core-manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
await writeFile(join(output, 'portable-app.json'), `${JSON.stringify({
  schemaVersion: 1, application: 'EasyCLIProxyAPI Private', version: await readAppVersion(),
  platform: targetOS, arch: targetArch, autoUpdate: false,
}, null, 2)}\n`);
console.log(`Private portable directory: ${output}`);
