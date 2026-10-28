use std::{fs, path::{Path, PathBuf}};

pub(crate) fn private_directory(path: PathBuf) -> Result<PathBuf, String> {
    fs::create_dir_all(&path).map_err(|error| error.to_string())?;
    let metadata = fs::symlink_metadata(&path).map_err(|error| error.to_string())?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err("Private application data must be a directory, not a symlink".into());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700))
            .map_err(|error| error.to_string())?;
    }
    Ok(path)
}

pub(crate) fn deny_auxiliary_network(feature: &str) -> Result<(), String> {
    Err(format!("{feature} is disabled in this private build. Only configured AI provider connections are supported."))
}

pub(crate) fn random_secret() -> String {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).expect("Secure random generation is required for local credentials");
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

pub(crate) fn verify_binary(path: &Path) -> Result<(), String> {
    verify_hash(path, env!("PRIVATE_CORE_BINARY_SHA256"))
}

pub(crate) fn verify_archive(path: &Path) -> Result<(), String> {
    verify_hash(path, env!("PRIVATE_CORE_ARCHIVE_SHA256"))
}

fn verify_hash(path: &Path, expected: &str) -> Result<(), String> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| format!("Cannot inspect private core {}: {error}", path.display()))?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err("The private core must be a regular file".to_string());
    }
    if super::sha256_file(path)? != expected {
        return Err("Core integrity check failed. Reinstall the bundled private core; stock or modified cores cannot run.".to_string());
    }
    Ok(())
}

pub(crate) fn secure_file(file: &fs::File) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        file.set_permissions(fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn private_secrets_are_distinct_and_not_the_shared_default() {
        let first = random_secret();
        let second = random_secret();
        assert_eq!(first.len(), 64);
        assert!(first.bytes().all(|byte| byte.is_ascii_hexdigit()));
        assert_ne!(first, second);
        assert_ne!(first, "123456");
    }

    #[test]
    fn auxiliary_connections_are_disabled() {
        assert!(deny_auxiliary_network("Update check").is_err());
    }

    #[test]
    fn altered_core_is_rejected() {
        let path = std::env::temp_dir().join(format!("private-core-test-{}", random_secret()));
        fs::write(&path, b"untrusted core").unwrap();
        assert!(verify_binary(&path).is_err());
        assert!(verify_archive(&path).is_err());
        fs::remove_file(path).unwrap();
    }
}

#[cfg(all(test, unix))]
mod private_config_tests {
    use super::*;
    use crate::*;
    use std::os::unix::fs::{symlink, PermissionsExt};

    #[test]
    fn private_config_rotates_shared_keys_and_preserves_custom_credentials() {
        let directory = std::env::temp_dir().join(format!("private-config-{}", random_secret()));
        let mut config = GuiConfigFile::default();
        config.management_secret_key = "123456".into();
        config.api_keys = vec![GuiApiKeyEntry { key: "123456".into(), remark: String::new() },
            GuiApiKeyEntry { key: "custom-provider-client-key".into(), remark: "retained".into() }];
        config.host = "0.0.0.0".into();
        config.allow_lan = true;
        config.plugins_enabled = true;
        config.auth_dir_user_selected = true;
        assert!(sanitize_gui_config_at(&mut config, &directory, &directory.join("oauth")).unwrap());
        assert_eq!(config.management_secret_key.len(), 64);
        assert_eq!(gui_api_key_values(&config.api_keys), vec!["custom-provider-client-key"]);
        assert_eq!(config.host, "127.0.0.1");
        assert!(!config.allow_lan && !config.plugins_enabled);
        let original = config.management_secret_key.clone();
        sanitize_gui_config_at(&mut config, &directory, &directory.join("oauth")).unwrap();
        assert_eq!(config.management_secret_key, original);
    }

    #[test]
    fn private_config_writes_are_owner_only_and_reject_symlinks() {
        let directory = private_directory(std::env::temp_dir().join(format!("private-files-{}", random_secret()))).unwrap();
        assert_eq!(fs::metadata(&directory).unwrap().permissions().mode() & 0o777, 0o700);
        let direct = directory.join("gui.toml");
        let atomic = directory.join("config.yaml");
        for (path, writer) in [(&direct, write_bytes_directly as fn(&Path, &[u8]) -> Result<(), String>), (&atomic, write_bytes_atomically)] {
            writer(path, b"test-credential").unwrap();
            assert_eq!(fs::metadata(path).unwrap().permissions().mode() & 0o777, 0o600);
            fs::set_permissions(path, fs::Permissions::from_mode(0o644)).unwrap();
            writer(path, b"replacement").unwrap();
            assert_eq!(fs::metadata(path).unwrap().permissions().mode() & 0o777, 0o600);
        }
        let link = directory.join("link.toml");
        symlink(&direct, &link).unwrap();
        assert!(write_bytes_directly(&link, b"overwrite").is_err());
        assert_eq!(fs::read(&direct).unwrap(), b"replacement");
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn private_build_accepts_only_its_built_artifacts() {
        let manifest: serde_json::Value = serde_json::from_slice(&fs::read(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../.build/private-core-artifacts/manifest.json")
        ).unwrap()).unwrap();
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
        verify_binary(&root.join(manifest["binary"].as_str().unwrap())).unwrap();
        verify_archive(&root.join(manifest["archive"].as_str().unwrap())).unwrap();
        let path = std::env::temp_dir().join(format!("private-core-link-{}", random_secret()));
        symlink(root.join(manifest["binary"].as_str().unwrap()), &path).unwrap();
        assert!(verify_binary(&path).is_err());
        fs::remove_file(path).unwrap();
    }
}
