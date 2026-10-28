# Private build validation

These results cover the macOS ARM64 private build. The GUI baseline is `9bbf63b22efd13247a2e4f7752cd27170750daf9`. The pinned core baseline is recorded in `core/source.lock.json`.

| Check | Result |
|---|---|
| Apply the complete patch to a fresh export of the pinned core | Passed |
| OAuth callback regression | Codex, Claude, Antigravity and the management forwarder reject connections through the host LAN address; localhost callbacks succeed |
| Focused Go privacy tests | 17 tests across 11 packages passed |
| Rust regression suite | 969 passed, zero failed, 10 ignored |
| TypeScript and production frontend build | Passed |
| Complete frontend suite | 1,013 passed, 32 skipped, eight failed |
| Original GUI baseline with the same frontend dependencies | The same eight frontend failure names reproduced |
| Private packaging CLI tests | Five passed |
| Manual-only build workflow test | Passed |
| macOS release, app bundle and portable package | Built successfully |
| Streaming and ordinary fake-provider requests | Passed with synthetic credentials |
| Auxiliary HTTP trap during startup and hostile configuration reload | Zero requests reached the trap |
| Forced periodic callbacks and disabled entry points | No HTTP transport calls; plugins and mDNS did not initialize |
| Installed GUI/core identity and local authentication | Expected hashes matched; authorized access succeeded and unauthorized access was rejected |
| Real-provider smoke check | One OAuth login and one ordinary inference request succeeded |
| Local dashboard | Displayed the new request after local usage statistics were enabled |

The eight baseline frontend failures concern IPC/mock inventories, button/localization/status inventories, CSS lint and OAuth quota priority display. They remain unresolved. Passing counts do not imply the entire frontend suite passes.

The callback regression reproduced LAN-accessible listeners before the fix and passed after binding them to `127.0.0.1`. It uses synthetic callbacks and the test host's own interface address, without a provider connection. It skips when no non-loopback IPv4 interface exists.

The synthetic core and GUI/core integration checks used OS sandbox profiles that blocked non-loopback outbound connections. The installed application does not carry a mandatory OS egress firewall. The HTTP trap is narrower than a complete syscall or DNS trace. Source tests exercise disabled periodic paths directly, without waiting for their normal timers.

The build records its source, patch, archive and executable digests in `.build/private-core-artifacts/manifest.json`. The GUI compiles the expected core digests into its executable. Local manifests, binaries, logs, account files, runtime settings and personal migration reports are excluded from this repository.

## Reproduce the source and synthetic checks

Build the core and GUI following [PRIVATE_BUILD.md](../PRIVATE_BUILD.md). The core builder applies the patch to clean pinned source, runs its privacy suite, compiles the core and verifies its macOS ad hoc signature before computing hashes.

Run the fake-provider integration test with:

```sh
python3 tests/private-core-smoke.py
```

Run packaging and workflow checks with:

```sh
bun test tests/portablePreparation.test.ts tests/privateRelease.test.ts
```

## Limits

- Source restrictions disable the inspected auxiliary paths. They do not prove the absence of unknown malicious behavior in every dependency or provider.
- The real-provider smoke check does not establish acceptance for every provider, account tier, model, streaming mode or quota path.
- Windows entry points are not ported to the private build. Windows/Linux builds and platform-specific permissions remain unverified.
- A core surviving a force-killed GUI requires manual shutdown before the GUI can start its own core. Untracked processes are deliberately not adopted or stopped; see [recovery instructions](../PRIVATE_BUILD.md#recovery-after-a-forced-gui-exit). Forced-crash recovery has not been accepted as automatic behavior.
- No independent cross-provider review or reproducible-build comparison is claimed.
- The build downloads public source and dependencies. User-launched browsers, external agents and configured proxies retain their own networking policies.
