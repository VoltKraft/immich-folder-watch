use safe_fs::{Directory, EntryKind, PublishError};
use std::ffi::OsStr;
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::Path;
use std::time::{Duration, SystemTime};

mod support;
use support::Synthetic;

fn sample_time(seconds: u64) -> SystemTime {
    SystemTime::UNIX_EPOCH + Duration::from_secs(seconds)
}

fn write_timed(path: &Path, contents: &[u8], time: SystemTime) {
    fs::write(path, contents).unwrap();
    fs::OpenOptions::new()
        .write(true)
        .open(path)
        .unwrap()
        .set_modified(time)
        .unwrap();
}

#[test]
fn contents_metadata_and_repair_keep_one_identity_when_a_leaf_name_changes() {
    let profile = Synthetic::new();
    let root = profile.root();
    let path = profile.0.join("image");
    let moved = profile.0.join("moved");
    let stamp = sample_time(1_600_000_000);
    write_timed(&path, b"original", stamp);
    let mut repair = root.open_for_time_repair(OsStr::new("image")).unwrap();
    let identity = repair.media().identity();
    assert!(repair.media().is_current_entry().unwrap());
    fs::rename(&path, &moved).unwrap();
    assert!(!repair.media().is_current_entry().unwrap());
    write_timed(&path, b"external", stamp);
    let replacement = root.open_file(OsStr::new("image")).unwrap();
    assert_ne!(identity, replacement.identity());
    assert_eq!(
        repair.media().metadata().unwrap().len(),
        replacement.metadata().unwrap().len()
    );
    assert_eq!(
        repair.media().metadata().unwrap().modified().unwrap(),
        replacement.metadata().unwrap().modified().unwrap()
    );
    let mut contents = String::new();
    repair.media().read_to_string(&mut contents).unwrap();
    assert_eq!(contents, "original");
    assert!(!repair.media().is_current_entry().unwrap());
    assert!(repair.set_times(stamp, sample_time(1_700_000_000)).is_err());
    assert_eq!(fs::read(&path).unwrap(), b"external");
    assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(), stamp);
    assert_eq!(fs::metadata(&moved).unwrap().modified().unwrap(), stamp);
}

#[test]
fn repair_updates_a_single_link_and_refuses_an_observed_hardlink() {
    let profile = Synthetic::new();
    let root = profile.root();
    let media = profile.0.join("image");
    fs::write(&media, b"synthetic").unwrap();
    let lease = root.open_for_time_repair(OsStr::new("image")).unwrap();
    let stamp = sample_time(1_650_000_000);
    lease.set_times(stamp, stamp).unwrap();
    assert_eq!(fs::metadata(&media).unwrap().modified().unwrap(), stamp);
    #[cfg(windows)]
    assert_eq!(fs::metadata(&media).unwrap().created().unwrap(), stamp);
    let alias = profile.0.join("alias");
    fs::hard_link(&media, &alias).unwrap();
    assert!(lease.set_times(stamp, sample_time(1_700_000_000)).is_err());
    assert_eq!(fs::metadata(&alias).unwrap().modified().unwrap(), stamp);
    assert_eq!(fs::read(alias).unwrap(), b"synthetic");
}

#[test]
fn root_and_child_leases_keep_original_directory_during_ordinary_replacement() {
    let profile = Synthetic::new();
    let original = profile.0.join("watch");
    let inside = original.join("album");
    let external = profile.0.join("other");
    let external_album = external.join("album");
    fs::create_dir_all(&inside).unwrap();
    fs::create_dir_all(&external_album).unwrap();
    fs::write(inside.join("sample"), b"inside").unwrap();
    let stamp = sample_time(1_600_000_000);
    write_timed(&external_album.join("sample"), b"outside", stamp);
    let root = Directory::open_root(&original).unwrap();
    let album = root.open_directory(OsStr::new("album")).unwrap();
    drop(root); // the operation retains the root and intermediate directory.
    let moved = profile.0.join("moved");
    let rename = fs::rename(&original, &moved);
    #[cfg(windows)]
    {
        let error = rename.unwrap_err();
        assert!(matches!(error.raw_os_error(), Some(5 | 32)), "{error}");
    }
    #[cfg(unix)]
    {
        rename.unwrap();
        fs::rename(&external, &original).unwrap();
    }
    let entries = album.entries(4).unwrap();
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0].name, "sample");
    assert_eq!(entries[0].kind, EntryKind::File);
    let mut bytes = Vec::new();
    album
        .open_file(OsStr::new("sample"))
        .unwrap()
        .read_to_end(&mut bytes)
        .unwrap();
    assert_eq!(bytes, b"inside");
    #[cfg(windows)]
    let sentinel = external_album.join("sample");
    #[cfg(unix)]
    let sentinel = original.join("album/sample");
    assert_eq!(fs::read(&sentinel).unwrap(), b"outside");
    assert_eq!(fs::metadata(sentinel).unwrap().modified().unwrap(), stamp);
}

#[test]
fn linked_directory_and_disguised_root_fail_closed_during_enumeration() {
    let profile = Synthetic::new();
    fs::create_dir(profile.0.join("real")).unwrap();
    fs::write(profile.0.join("real/sentinel"), b"preserved").unwrap();
    #[cfg(unix)]
    std::os::unix::fs::symlink("real", profile.0.join("link")).unwrap();
    #[cfg(windows)]
    {
        // cmd.exe cannot use a UNC current directory. Only create the junction
        // on the dedicated backing volume. All tested lease calls use the UNC.
        let directory = match support::smb_fixture_name() {
            Some(name) => std::path::PathBuf::from(
                std::env::var_os("RUNNER_TEMP").expect("disposable SMB backing directory"),
            )
            .join(name)
            .join(profile.0.file_name().unwrap()),
            None => profile.0.clone(),
        };
        let result = std::process::Command::new("cmd.exe")
            .args(["/d", "/c", "mklink", "/j", "link", "real"])
            .current_dir(directory)
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
    }
    let root = profile.root();
    let link = profile.0.join("link");
    assert!(Directory::open_root(&link).is_err());
    assert!(Directory::open_root(&link.join(".")).is_err());
    assert!(root.open_directory(OsStr::new("link")).is_err());
    assert!(root.entries(10).is_err());
    assert_eq!(
        fs::read(profile.0.join("real/sentinel")).unwrap(),
        b"preserved"
    );
}

#[test]
fn reserved_names_and_invalid_components_never_authorize_media() {
    let profile = Synthetic::new();
    let root = profile.root();
    fs::create_dir(profile.0.join(".IFW-internal-private")).unwrap();
    fs::write(profile.0.join("Grüße-雪"), b"content").unwrap();
    for invalid in [
        "",
        ".",
        "..",
        "a/b",
        ".iFw-Internal-private",
        "a/../b",
        "a\0b",
    ] {
        assert!(root.open_file(OsStr::new(invalid)).is_err());
        assert!(root.open_directory(OsStr::new(invalid)).is_err());
    }
    #[cfg(windows)]
    for invalid in [r"a\b", "Grüße-雪:stream", "name.", "name "] {
        assert!(root.open_file(OsStr::new(invalid)).is_err());
    }
    assert!(root.entries(1).is_err());
    let entries = root.entries(2).unwrap();
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0].name, "Grüße-雪");
}

#[test]
fn independent_scans_read_all_directory_batches() {
    let profile = Synthetic::new();
    let root = profile.root();
    for n in 0..400 {
        File::create(profile.0.join(format!("{n:04}-{}", "a".repeat(100)))).unwrap();
    }
    std::thread::scope(|scope| {
        let scan = || {
            let mut entries: Vec<_> = root
                .entries(400)
                .unwrap()
                .into_iter()
                .map(|e| e.name)
                .collect();
            entries.sort();
            entries.dedup();
            assert_eq!(entries.len(), 400);
            entries
        };
        let other = scope.spawn(scan);
        assert_eq!(scan(), other.join().unwrap());
    });
}

#[cfg(target_os = "linux")]
#[test]
fn locked_and_special_files_are_refused_without_reading_their_data() {
    let profile = Synthetic::new();
    let root = profile.root();
    let locked = File::create(profile.0.join("writing")).unwrap();
    locked.try_lock().unwrap();
    assert!(root.open_file(OsStr::new("writing")).is_err());
    assert!(
        std::process::Command::new("mkfifo")
            .arg(profile.0.join("pipe"))
            .status()
            .unwrap()
            .success()
    );
    assert!(root.open_file(OsStr::new("pipe")).is_err());
    std::os::unix::fs::symlink("writing", profile.0.join("link")).unwrap();
    assert!(root.open_file(OsStr::new("link")).is_err());
}

#[test]
fn competing_stages_publish_one_complete_payload_without_overwriting() {
    let profile = Synthetic::new();
    let root = profile.root();
    let dest = OsStr::new("new-image");
    let mut first = root.begin_download(dest).unwrap();
    let mut second = root.begin_download(dest).unwrap();
    first.write_all(b"winner").unwrap();
    second.write_all(b"other content").unwrap();
    assert!(root.entries(10).unwrap().is_empty());
    first.publish().unwrap();
    let error = second.publish().unwrap_err();
    assert!(!error.requires_reconciliation());
    assert!(matches!(error, PublishError::BeforeRename(e)
        if e.kind() == std::io::ErrorKind::AlreadyExists));
    assert_eq!(fs::read(profile.0.join(dest)).unwrap(), b"winner");
    assert_eq!(root.entries(10).unwrap().len(), 1);
    assert!(profile.transaction_directories().is_empty());
}

#[test]
fn acknowledged_publication_with_cleanup_failure_keeps_both_destination_and_unrelated_entry() {
    let profile = Synthetic::new();
    let root = profile.root();
    let mut download = root.begin_download(OsStr::new("image")).unwrap();
    download.write_all(b"published").unwrap();
    let directories = profile.transaction_directories();
    assert_eq!(directories.len(), 1);
    let extra = directories[0].join("extra");
    fs::write(&extra, b"preserve unrelated contents").unwrap();
    let error = download.publish().unwrap_err();
    assert!(matches!(error, PublishError::AfterRename(_)));
    assert!(error.requires_reconciliation());
    assert_eq!(fs::read(profile.0.join("image")).unwrap(), b"published");
    assert_eq!(fs::read(extra).unwrap(), b"preserve unrelated contents");
}

#[test]
fn cancelled_or_dropped_stage_leaves_no_media_or_payload() {
    let profile = Synthetic::new();
    let root = profile.root();
    for cancel in [false, true] {
        let mut stage = root.begin_download(OsStr::new("new-image")).unwrap();
        stage.write_all(b"incomplete").unwrap();
        if cancel {
            stage.cancel().unwrap();
        }
    }
    assert!(root.entries(10).unwrap().is_empty());
    #[cfg(unix)]
    {
        let outer: Vec<_> = fs::read_dir(&profile.0)
            .unwrap()
            .map(|e| e.unwrap().path())
            .collect();
        assert_eq!(outer.len(), 1);
        assert_eq!(fs::read_dir(&outer[0]).unwrap().count(), 0);
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(&outer[0]).unwrap().permissions().mode() & 0o777,
            0o700
        );
    }
    #[cfg(windows)]
    assert_eq!(fs::read_dir(&profile.0).unwrap().count(), 0);
}

#[test]
fn pending_publication_uses_the_original_parent_after_a_directory_move() {
    let profile = Synthetic::new();
    let path = profile.0.join("album");
    fs::create_dir(&path).unwrap();
    let moved = profile.0.join("moved");
    let root = profile.root();
    let album = root.open_directory(OsStr::new("album")).unwrap();
    let mut stage = album.begin_download(OsStr::new("image")).unwrap();
    stage.write_all(b"authorized").unwrap();
    drop(album);
    let rename = fs::rename(&path, &moved);
    #[cfg(windows)]
    {
        let error = rename.unwrap_err();
        assert!(matches!(error.raw_os_error(), Some(5 | 32)), "{error}");
        stage.publish().unwrap();
        assert_eq!(fs::read(path.join("image")).unwrap(), b"authorized");
    }
    #[cfg(unix)]
    {
        rename.unwrap();
        fs::create_dir(&path).unwrap();
        let sentinel = path.join("image");
        let stamp = sample_time(1_630_000_000);
        write_timed(&sentinel, b"outside", stamp);
        stage.publish().unwrap();
        assert_eq!(fs::read(moved.join("image")).unwrap(), b"authorized");
        assert_eq!(fs::read(&sentinel).unwrap(), b"outside");
        assert_eq!(fs::metadata(sentinel).unwrap().modified().unwrap(), stamp);
    }
}

#[cfg(target_os = "linux")]
#[test]
fn replacing_outer_name_cannot_redirect_cancellation_or_publication() {
    let profile = Synthetic::new();
    let root = profile.root();
    let stage = root.begin_download(OsStr::new("cancelled")).unwrap();
    let outer = fs::read_dir(&profile.0)
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    let moved = profile.0.join(".ifw-internal-moved");
    fs::rename(&outer, &moved).unwrap();
    fs::create_dir(&outer).unwrap();
    let sentinel = outer.join("payload");
    let stamp = sample_time(1_655_000_000);
    write_timed(&sentinel, b"outside", stamp);
    stage.cancel().unwrap();
    let mut next = root.begin_download(OsStr::new("image")).unwrap();
    next.write_all(b"inside").unwrap();
    next.publish().unwrap();
    assert_eq!(fs::read(profile.0.join("image")).unwrap(), b"inside");
    assert_eq!(fs::read_dir(moved).unwrap().count(), 0);
    assert_eq!(fs::read(&sentinel).unwrap(), b"outside");
    assert_eq!(fs::metadata(sentinel).unwrap().modified().unwrap(), stamp);
}

#[cfg(target_os = "linux")]
#[test]
fn active_stage_survives_container_eviction_and_revisit_creates_a_fresh_container() {
    let profile = Synthetic::new();
    let root = profile.root();
    let album_path = profile.0.join("album");
    fs::create_dir(&album_path).unwrap();
    let album = root.open_directory(OsStr::new("album")).unwrap();
    let mut held = album.begin_download(OsStr::new("image")).unwrap();
    held.write_all(b"still-live").unwrap();
    for n in 0..64 {
        let name = format!("other-{n}");
        fs::create_dir(profile.0.join(&name)).unwrap();
        root.open_directory(OsStr::new(&name))
            .unwrap()
            .begin_download(OsStr::new("probe"))
            .unwrap()
            .cancel()
            .unwrap();
    }
    album
        .begin_download(OsStr::new("second"))
        .unwrap()
        .cancel()
        .unwrap();
    assert_eq!(fs::read_dir(&album_path).unwrap().count(), 2);
    held.publish().unwrap();
    assert_eq!(fs::read(album_path.join("image")).unwrap(), b"still-live");
}

#[cfg(target_os = "linux")]
#[test]
fn changed_container_protection_stops_new_stages() {
    use std::os::unix::fs::PermissionsExt;
    let profile = Synthetic::new();
    let root = profile.root();
    root.begin_download(OsStr::new("initial"))
        .unwrap()
        .cancel()
        .unwrap();
    let container = fs::read_dir(&profile.0)
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    fs::set_permissions(&container, fs::Permissions::from_mode(0o755)).unwrap();
    assert!(root.begin_download(OsStr::new("image")).is_err());
    assert_eq!(fs::read_dir(container).unwrap().count(), 0);
}

#[cfg(windows)]
#[test]
fn reported_windows_short_name_cannot_authorize_a_reserved_directory() {
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    use std::path::PathBuf;
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetShortPathNameW(path: *const u16, short: *mut u16, capacity: u32) -> u32;
    }
    let profile = Synthetic::new();
    let internal = profile.0.join(".ifw-internal-existing");
    fs::create_dir(&internal).unwrap();
    fs::write(internal.join("marker"), b"reserved alias target").unwrap();
    let input: Vec<_> = internal.as_os_str().encode_wide().chain([0]).collect();
    let mut units = vec![0u16; 32768];
    // SAFETY: input terminates in NUL and the output array has the indicated capacity.
    let result =
        unsafe { GetShortPathNameW(input.as_ptr(), units.as_mut_ptr(), units.len() as u32) }
            as usize;
    assert!(result != 0 && result < units.len());
    let short = PathBuf::from(std::ffi::OsString::from_wide(&units[..result]));
    let alias = short.file_name().unwrap();
    let long = internal.file_name().unwrap();
    let distinct = !alias
        .as_encoded_bytes()
        .eq_ignore_ascii_case(long.as_encoded_bytes());
    println!("distinct_short_name={distinct}");
    let setting = std::env::var_os("IFW_RUST_REQUIRE_WINDOWS_SHORT_NAME");
    let required = match setting.as_deref().map(OsStr::as_encoded_bytes) {
        None | Some(b"0") => false,
        Some(b"1") => true,
        _ => panic!("IFW_RUST_REQUIRE_WINDOWS_SHORT_NAME must be 0 or 1"),
    };
    if !distinct {
        // Volumes with 8.3 generation disabled return the original spelling.
        println!("short_name_denial_verified=false");
        assert!(
            !required,
            "the provisioned NTFS fixture must produce a distinct 8.3 alias"
        );
        return;
    }
    assert_eq!(
        fs::read(profile.0.join(alias).join("marker")).unwrap(),
        b"reserved alias target"
    );
    let error = profile.root().open_directory(alias).unwrap_err();
    assert_eq!(error.kind(), std::io::ErrorKind::PermissionDenied);
    println!("short_name_denial_verified=true");
}
