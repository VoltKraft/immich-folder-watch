use super::Directory;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

pub(crate) struct Synthetic(pub(crate) PathBuf);

#[cfg(windows)]
pub(crate) fn smb_fixture_name() -> Option<String> {
    let id = std::env::var_os("IFW_RUST_SMB_FIXTURE")?;
    let id = id.to_str().expect("ASCII SMB fixture identifier");
    assert!(id.len() == 32 && id.bytes().all(|b| b.is_ascii_hexdigit()));
    Some(format!("IfwRustQa{id}"))
}

impl Synthetic {
    pub(crate) fn new() -> Self {
        static SEQUENCE: AtomicU64 = AtomicU64::new(0);
        let base = std::env::temp_dir();
        #[cfg(windows)]
        let base = smb_fixture_name().map_or(base, |name| {
            println!("smb_fixture={name}");
            PathBuf::from(format!(r"\\localhost\{name}$"))
        });
        loop {
            let serial = SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = base.join(format!("ifw-rust-fs-test-{}-{serial}", std::process::id()));
            let builder = fs::DirBuilder::new();
            #[cfg(unix)]
            let mut builder = builder;
            #[cfg(unix)]
            std::os::unix::fs::DirBuilderExt::mode(&mut builder, 0o700);
            match builder.create(&path) {
                Ok(()) => return Self(path),
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(e) => panic!("create synthetic profile: {e}"),
            }
        }
    }

    pub(crate) fn root(&self) -> Directory {
        Directory::open_root(&self.0).unwrap()
    }

    pub(crate) fn transaction_directories(&self) -> Vec<PathBuf> {
        fn internal_children(directory: &Path) -> Vec<PathBuf> {
            fs::read_dir(directory)
                .unwrap()
                .map(Result::unwrap)
                .filter(|entry| {
                    entry
                        .file_name()
                        .as_encoded_bytes()
                        .starts_with(b".ifw-internal-")
                })
                .map(|entry| entry.path())
                .collect()
        }
        let directories = internal_children(&self.0);
        #[cfg(target_os = "linux")]
        let directories = directories
            .iter()
            .flat_map(|outer| internal_children(outer))
            .collect();
        directories
    }
}

impl Drop for Synthetic {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).expect("clean up the synthetic profile");
    }
}
