use sha2::{Digest, Sha256};
use std::{fs, path::Path};

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn read(root: &Path, name: &str) -> Vec<u8> {
    let path = root.join(name);
    println!("cargo:rerun-if-changed={}", path.display());
    fs::read(&path).unwrap_or_else(|error| panic!("Missing private build input {}: {error}. Run python3 scripts/build-private-core.py first.", path.display()))
}

fn main() {
    let root = Path::new("..");
    let lock_bytes = read(root, "core/source.lock.json");
    let lock: serde_json::Value = serde_json::from_slice(&lock_bytes).expect("Invalid core source lock");
    let manifest: serde_json::Value = serde_json::from_slice(&read(root, ".build/private-core-artifacts/manifest.json"))
        .expect("Invalid private core manifest");
    assert_eq!(manifest["schema"], 1, "Unsupported private core manifest");
    assert_eq!(manifest["sourceCommit"], lock["commit"], "Private core source changed; rebuild it");
    assert_eq!(manifest["privacyRevision"], lock["privacyRevision"], "Private core policy changed; rebuild it");
    assert_eq!(manifest["lockSha256"], digest(&lock_bytes), "Private core lock changed; rebuild it");
    let mut patches = Sha256::new();
    for patch in lock["patches"].as_array().expect("Missing core patch list") {
        let name = patch.as_str().expect("Invalid patch name");
        patches.update(name.as_bytes());
        patches.update([0]);
        patches.update(read(root, &format!("core/patches/{name}")));
    }
    assert_eq!(manifest["patchSetSha256"], format!("{:x}", patches.finalize()), "Core patches changed; rebuild it");
    let target_os = std::env::var("CARGO_CFG_TARGET_OS").unwrap();
    let platform = if target_os == "macos" { "darwin" } else { &target_os };
    let target_arch = std::env::var("CARGO_CFG_TARGET_ARCH").unwrap();
    let arch = match target_arch.as_str() { "aarch64" => "arm64", "x86_64" => "amd64", other => other };
    assert_eq!(manifest["platform"], platform, "Private core platform mismatch");
    assert_eq!(manifest["arch"], arch, "Private core architecture mismatch");
    for (field, expected, env_name) in [
        ("binary", "binarySha256", "PRIVATE_CORE_BINARY_SHA256"),
        ("archive", "archiveSha256", "PRIVATE_CORE_ARCHIVE_SHA256"),
    ] {
        let actual = digest(&read(root, manifest[field].as_str().expect("Missing artifact path")));
        assert_eq!(manifest[expected], actual, "Private core artifact changed; rebuild it");
        println!("cargo:rustc-env={env_name}={actual}");
    }
    tauri_build::build()
}
