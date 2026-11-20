use super::Directory;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

pub(crate) struct Synthetic(pub(crate) PathBuf);

impl Synthetic {
    pub(crate) fn new() -> Self {
        static SEQUENCE: AtomicU64 = AtomicU64::new(0);
        loop {
            let serial = SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir()
                .join(format!("ifw-rust-fs-test-{}-{serial}", std::process::id()));
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
