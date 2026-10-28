import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test } from 'bun:test';

const archiveName = 'CLIProxyAPI_8.0.44_windows_amd64.zip';
const digest = (bytes: string) => createHash('sha256').update(bytes).digest('hex');
async function fixture(run: (root: string) => Promise<void>) {
  const root = await mkdtemp(join(tmpdir(), 'easycli-private-package-'));
  try {
    for (const directory of ['scripts','src-tauri','cpa-core','core/patches','.build/private-core-artifacts','bin-work/private-data']) {
      await mkdir(join(root, directory), { recursive: true });
    }
    for (const script of ['portable.mjs','version.mjs']) {
      await copyFile(fileURLToPath(new URL(`../scripts/${script}`, import.meta.url)), join(root, 'scripts', script));
    }
    await writeFile(join(root,'src-tauri/Cargo.toml'), '[package]\nname = "cpa-gui"\nversion = "0.3.6"\n');
    await writeFile(join(root,'core-version.txt'), '8.0.44\n');
    await writeFile(join(root,'cpa-gui.exe'), 'fixture-gui');
    await writeFile(join(root,'core/patches/policy.patch'), 'fixture-policy');
    const lock = JSON.stringify({ commit:'fixture-commit', privacyRevision:1, version:'8.0.44', patches:['policy.patch'] });
    await writeFile(join(root,'core/source.lock.json'), lock);
    await writeFile(join(root,'cpa-core',archiveName), 'fixture-archive');
    await writeFile(join(root,'.build/private-core-artifacts/cli-proxy-api.exe'), 'fixture-core');
    await writeFile(join(root,'.build/private-core-artifacts/manifest.json'), JSON.stringify({
      schema:1, sourceCommit:'fixture-commit', privacyRevision:1, lockSha256:digest(lock),
      patchSetSha256:digest('policy.patch\0fixture-policy'), platform:'windows', arch:'amd64',
      binary:'.build/private-core-artifacts/cli-proxy-api.exe', binarySha256:digest('fixture-core'),
      archive:`cpa-core/${archiveName}`, archiveSha256:digest('fixture-archive'),
    }));
    await run(root);
  } finally {
    await rm(root, { recursive:true, force:true });
  }
}
function prepare(root: string, download = false) {
  return spawnSync('node',[join(root,'scripts/portable.mjs'),'--binary',join(root,'cpa-gui.exe'),
    '--output',join(root,'bin-work'),'--os','windows','--arch','amd64','--download',String(download)],
    { encoding:'utf8', cwd:root });
}
test('private packages contain the verified local archive and preserve separate runtime data on rebuild', async () => {
  await fixture(async root => {
    await writeFile(join(root,'bin-work/private-data/fixture.toml'),'local-user-data');
    for (let i=0;i<2;i++) {
      const result = prepare(root);
      expect(result.status).toBe(0);
      expect(result.stderr).toBe('');
      expect(await readFile(join(root,'bin-work/cpa-core',archiveName),'utf8')).toBe('fixture-archive');
      expect(await readFile(join(root,'bin-work/private-data/fixture.toml'),'utf8')).toBe('local-user-data');
      expect(JSON.parse(await readFile(join(root,'bin-work/portable-app.json'),'utf8')).autoUpdate).toBe(false);
    }
  });
});
for (const [name,path] of [
  ['archive',`cpa-core/${archiveName}`],
  ['binary','.build/private-core-artifacts/cli-proxy-api.exe'],
  ['patch','core/patches/policy.patch'],
] as const) {
  test(`private packaging rejects a changed ${name}`, async () => {
    await fixture(async root => {
      await writeFile(join(root,path),'replaced-with-untrusted-bytes');
      expect(prepare(root).status).not.toBe(0);
    });
  });
}
test('private packaging rejects missing provenance and online download requests', async () => {
  await fixture(async root => {
    expect(prepare(root,true).stderr).toContain('Online core downloads are disabled');
    await rm(join(root,'.build/private-core-artifacts/manifest.json'));
    expect(prepare(root).status).not.toBe(0);
  });
});
