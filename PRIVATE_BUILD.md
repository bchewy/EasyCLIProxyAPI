# EasyCLIProxyAPI Private

This fork permits the AI providers you explicitly configure and use. It disables unrelated runtime networking. This is a local privacy build, not a claim that every provider or dependency is trustworthy.

## Allowed behavior

- Provider authentication, token refresh, quota checks, model requests and inference for configured accounts/endpoints.
- Local GUI/core communication and local usage records.
- Explicit configuration of an upstream proxy and local agent integrations. Programs you choose to launch have their own networking and telemetry policies.

To show completed requests in the dashboard, enable **Advanced Features → Logs & diagnostics → Usage statistics**. These records stay in the local usage database. Request/response body logging is a separate setting. Requests made while statistics were disabled cannot be recovered into the dashboard.

## Disabled behavior

- GUI/core online update checks, downloads, fallback mirrors and automatic release installation.
- Remote model catalogs and cached upstream Codex instruction overrides. The bundled catalog and your local customizations remain available.
- Management-panel downloads and the browser management panel.
- Plugin loading, installation, store queries and plugin webviews.
- Pi package registry/install/update operations and automatic execution of discovered agents just to read their version.
- Remote pricing downloads, auxiliary Antigravity/xAI version lookups and public-IP lookups.
- Home mode, remote Git/Postgres/object credential stores, `.env` loading, environment management-password overrides, and mDNS discovery.
- Claude cloaking mode and proxy-identifying header suppression. Provider-required wire formats and OAuth headers remain.

The core applies this policy during initial loading, optional configuration fallbacks and configuration reload. Disabled network entry points refuse direct calls too. Configuration cannot turn these capabilities back on.

## Local credentials and core identity

New local API and management credentials use 32 random bytes each. The old shared `123456` default is migrated. Unix configuration writers use owner-only permissions; the private application data directory is `0700`. The listener is fixed to loopback. Management HTTP clients validate TLS certificates.

The GUI checks its compiled SHA-256 expectations before installing an archive or starting the core. Stock, modified, missing and symlinked core files are rejected. A version number or an adjacent checksum file cannot authorize another binary. Existing processes are not adopted.

The macOS app has a separate identifier and data directory:

```text
com.bchewy.easycliproxyapi.private
~/Library/Application Support/com.bchewy.easycliproxyapi.private/
```

Portable builds use `private-data` beside their executable. Existing upstream application data is not imported automatically. An existing service on port 8317 must be stopped by you, or the private app must be assigned a different port, before both can run.

## Build

The separate Go core is pinned in `core/source.lock.json`. Its complete modifications, dependency updates and privacy tests are in `core/patches/provider-only.patch`.

On macOS, with Go, Rust, Python 3.12+ and Bun installed:

```sh
bash build.sh
```

The first build downloads public source and locked build dependencies. Runtime restrictions do not make building offline. No registry lifecycle scripts run during the Bun install.

To use an existing clone containing the pinned core commit:

```sh
bash build.sh --source /path/to/CLIProxyAPI
```

For an app bundle after the private core has been built:

```sh
bun tauri build --bundles app
```

Outputs:

- `bin-work/EasyCLIProxyAPI` plus the adjacent bundled archive and manifests.
- `src-tauri/target/release/bundle/macos/EasyCLIProxyAPI Private.app` when bundling is requested.

The build signs the core ad hoc on macOS **before** hashing and compiling the GUI. Changing or re-signing that core requires rebuilding the manifest and GUI together. The manifest identifies the trusted local build inputs; it is not a third-party signed supply-chain attestation. The build fails if the manifest, source lock, patch set, platform, architecture or artifact digests disagree.

The GitHub workflow is manual, builds a macOS ARM64 artifact and has read-only repository permission. It does not create releases, merge PRs, retarget branches or publish builds automatically. Other targets have not been built or accepted in this work.

## Verification

The source builder runs 14 focused privacy tests across nine Go packages. Additional Rust tests cover credentials, file permissions, stale remote instructions, process adoption and artifact rejection. Packaging tests exercise the real packaging CLI with disposable fixtures.

Run the synthetic core integration test:

```sh
python3 tests/private-core-smoke.py
```

It uses local fake-provider and auxiliary-trap servers, synthetic keys, hostile old configuration and environment values, configuration reload, and streaming/non-streaming completions. On macOS it adds an OS sandbox allowing outbound loopback connections only. It never uses a real account.

See [private build validation](docs/private-build-validation.md) for test results and acceptance limits. Source restrictions are not a general OS firewall. A macOS provider OAuth login, one ordinary inference request and the local dashboard were verified. Full provider coverage, full UI coverage and Windows/Linux acceptance are not claimed.
