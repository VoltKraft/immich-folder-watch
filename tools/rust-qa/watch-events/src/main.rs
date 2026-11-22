//! Pipe-controlled development subject for a freshly created synthetic directory.

use native_watch_hints::{Inventory, Scope, Snapshot, Watch};
use std::collections::BTreeSet;
use std::fs::{self, File};
use std::io::{self, BufRead, Write};
use std::path::Path;
use std::time::{Duration, Instant};

// Linux UAPI assigns different O_DIRECTORY and O_NOFOLLOW bits on these ABIs.
#[cfg(all(target_os = "linux", target_arch = "x86_64"))]
const DIRECTORY_FLAGS: (i32, i32) = (0x10000, 0x20000);
#[cfg(all(target_os = "linux", target_arch = "aarch64"))]
const DIRECTORY_FLAGS: (i32, i32) = (0x4000, 0x8000);

fn directory(path: &Path) -> io::Result<File> {
    let mut options = File::options();
    options.read(true);
    #[cfg(target_os = "linux")]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(DIRECTORY_FLAGS.0 | DIRECTORY_FLAGS.1);
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options
            .access_mode(1 | 0x80 | 0x10_0000)
            .share_mode(3)
            .custom_flags(0x0200_0000 | 0x20_0000);
    }
    let file = options.open(path);
    #[cfg(windows)]
    if let Err(error) = &file {
        eprintln!("WATCH_OPERATION open synthetic directory {path:?} {error}");
    }
    file
}

#[cfg(target_os = "linux")]
fn fixture_descendants(root: &File) -> io::Result<Vec<File>> {
    use std::os::fd::AsRawFd;
    use std::os::unix::fs::{DirEntryExt, MetadataExt};
    let mut directories: Vec<File> = Vec::new();
    let mut index = 0;
    while index <= directories.len() {
        let parent = if index == 0 {
            root
        } else {
            &directories[index - 1]
        };
        let anchor = format!("/proc/self/fd/{}", parent.as_raw_fd());
        for entry in fs::read_dir(anchor)? {
            let entry = entry?;
            let kind = entry.file_type()?;
            if kind.is_dir() {
                if directories.len() >= 1023 {
                    return Err(io::Error::other(
                        "synthetic directory inventory exceeded its bound",
                    ));
                }
                // Open this one enumerated name below the still-live parent fd.
                let file = directory(&entry.path())?;
                if file.metadata()?.ino() != entry.ino() {
                    return Err(io::Error::other(
                        "synthetic directory changed during registration inventory",
                    ));
                }
                directories.push(file);
            } else if !kind.is_file() {
                return Err(io::Error::other(
                    "unexpected object in synthetic directory inventory",
                ));
            }
        }
        index += 1;
    }
    Ok(directories)
}

#[cfg(target_os = "linux")]
fn confirm(watch: &Watch, root: &File) -> io::Result<bool> {
    // Reacquire the selected synthetic root for an independent post-arm inventory.
    let view = directory(Path::new("source")).and_then(|fresh_root| {
        let children = fixture_descendants(&fresh_root)?;
        Ok((fresh_root, children))
    });
    match view {
        Ok((fresh_root, children)) => watch.confirm_directory_set(&fresh_root, Some(&children)),
        Err(error) => {
            watch.confirm_directory_set(root, None)?;
            Err(error)
        }
    }
}

#[cfg(target_os = "linux")]
fn modules() -> io::Result<BTreeSet<String>> {
    let maps = fs::read_to_string("/proc/self/maps")?;
    Ok(maps
        .lines()
        .filter_map(|line| {
            let mut fields = line.split_whitespace();
            let perms = fields.nth(1)?;
            let path = fields.nth(3)?;
            (perms.as_bytes().get(2) == Some(&b'x')).then_some(path)
        })
        .filter(|path| path.starts_with('/') && path.contains(".so"))
        .map(str::to_owned)
        .collect())
}

#[cfg(windows)]
fn modules() -> io::Result<BTreeSet<String>> {
    use std::ffi::c_void;
    use std::ptr::null_mut;
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetCurrentProcess() -> *mut c_void;
        fn K32EnumProcessModules(
            process: *mut c_void,
            modules: *mut *mut c_void,
            bytes: u32,
            needed: *mut u32,
        ) -> i32;
        fn GetModuleFileNameW(module: *mut c_void, filename: *mut u16, chars: u32) -> u32;
    }
    let mut handles = [null_mut(); 256];
    let mut bytes = 0;
    // SAFETY: query only the current fixture process into bounded pointer storage.
    if unsafe {
        K32EnumProcessModules(
            GetCurrentProcess(),
            handles.as_mut_ptr(),
            size_of_val(&handles) as u32,
            &mut bytes,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    if bytes as usize > size_of_val(&handles)
        || !(bytes as usize).is_multiple_of(size_of::<*mut c_void>())
    {
        return Err(io::Error::other("incomplete fixture module inventory"));
    }
    let mut modules = BTreeSet::new();
    for &handle in &handles[..bytes as usize / size_of::<*mut c_void>()] {
        let mut wide = [0u16; 2048];
        // SAFETY: the module belongs to this process and the buffer has the declared size.
        let count =
            unsafe { GetModuleFileNameW(handle, wide.as_mut_ptr(), wide.len() as u32) } as usize;
        if count == 0 || count >= wide.len() {
            return Err(io::Error::other("incomplete fixture module name"));
        }
        let name = String::from_utf16(&wide[..count]).map_err(io::Error::other)?;
        if name.to_ascii_lowercase().ends_with(".dll") {
            modules.insert(name);
        }
    }
    Ok(modules)
}

fn state(label: &str, s: Snapshot) {
    println!(
        "{label} {} {} {} {} {} {} {}",
        s.generation,
        s.acknowledged,
        s.reasons,
        u8::from(s.requires_registration),
        s.queued,
        s.peak_queued,
        s.coalesced
    );
}

fn main() -> io::Result<()> {
    let token = std::env::var("IFW_WATCH_FIXTURE").map_err(io::Error::other)?;
    if token.len() != 32
        || !token.bytes().all(|b| b.is_ascii_hexdigit())
        || fs::read_to_string("owner")? != token
    {
        return Err(io::Error::other("expected a fresh isolated watch fixture"));
    }
    let mut args = std::env::args().skip(1);
    let mode = args
        .next()
        .ok_or_else(|| io::Error::other("expected source mode"))?;
    let capacity = args
        .next()
        .ok_or_else(|| io::Error::other("expected queue size"))?
        .parse()
        .map_err(io::Error::other)?;
    let root = directory(Path::new("source"))?;
    #[cfg(target_os = "linux")]
    let mut nested = if mode == "partial" || mode == "direct" {
        Vec::new()
    } else {
        fixture_descendants(&root)?
    };
    #[cfg(windows)]
    let mut nested = Vec::new();
    let scope = match mode.as_str() {
        "direct" => Scope::Direct,
        "tree" | "expanded" | "partial" | "rejected-child" | "registration-gap" => {
            #[cfg(windows)]
            if mode != "partial" {
                nested.push(directory(Path::new("source/nested"))?);
            }
            #[cfg(windows)]
            if mode == "expanded" {
                nested.push(directory(Path::new("source/added"))?);
            }
            if mode == "rejected-child" {
                nested.push(File::open("source/regular.jpg")?);
            }
            if mode == "registration-gap" {
                println!("CAPTURED {}", nested.len());
                io::stdout().flush()?;
                let mut command = String::new();
                io::stdin().read_line(&mut command)?;
                if command.trim_end() != "ARM" {
                    return Err(io::Error::other(
                        "expected the fixture registration barrier",
                    ));
                }
            }
            Scope::Tree {
                descendants: &nested,
                inventory_complete: mode != "partial",
            }
        }
        _ => return Err(io::Error::other("unknown fixture mode")),
    };
    let mut watch = Watch::start(&root, scope, capacity)?;
    #[cfg(windows)]
    let mut registration_inputs = Some((root, nested));
    #[cfg(target_os = "linux")]
    if matches!(mode.as_str(), "tree" | "expanded") && !confirm(&watch, &root)? {
        return Err(io::Error::other(
            "fresh synthetic registration does not cover the second inventory",
        ));
    }
    let mut inventory: Option<Inventory> = None;
    state("READY", watch.snapshot());
    io::stdout().flush()?;
    for line in io::stdin().lock().lines() {
        let line = line?;
        let fields: Vec<_> = line.split_ascii_whitespace().collect();
        match fields.as_slice() {
            ["WAIT", generation, ms] => {
                let generation = generation.parse().map_err(io::Error::other)?;
                let timeout =
                    Duration::from_millis(ms.parse::<u64>().map_err(io::Error::other)?.min(5000));
                state("STATE", watch.wait_after(generation, timeout));
            }
            ["STATE"] => state("STATE", watch.snapshot()),
            #[cfg(windows)]
            ["RELEASE_INPUT_HANDLES"] => {
                let inputs = registration_inputs
                    .take()
                    .ok_or_else(|| io::Error::other("registration inputs already released"))?;
                drop(inputs);
                println!("INPUT_HANDLES_RELEASED");
            }
            #[cfg(target_os = "linux")]
            ["DIRFLAGS"] => println!("DIRFLAGS {} {}", DIRECTORY_FLAGS.0, DIRECTORY_FLAGS.1),
            #[cfg(target_os = "linux")]
            ["CONFIRM"] => println!("CONFIRMED {}", u8::from(confirm(&watch, &root)?)),
            ["BEGIN"] if inventory.is_none() => {
                let started = watch.begin_inventory();
                state("BEGIN", started.observed());
                inventory = Some(started);
            }
            ["END", result @ ("complete" | "partial")] => {
                let started = inventory
                    .take()
                    .ok_or_else(|| io::Error::other("missing inventory"))?;
                println!("END {}", u8::from(started.finish(*result == "complete")));
            }
            ["CANCEL"] => {
                let started = inventory
                    .take()
                    .ok_or_else(|| io::Error::other("missing inventory"))?;
                drop(started);
                println!("CANCELLED");
            }
            ["MODULES"] => {
                for module in modules()? {
                    println!("MODULE {module}");
                }
                println!("MODULES_DONE");
            }
            [command @ ("STOP" | "JOIN")] => {
                let start = Instant::now();
                watch.stop_and_join(Duration::from_secs(5))?;
                println!("STOPPED {}", start.elapsed().as_micros());
                if *command == "STOP" {
                    return Ok(());
                }
            }
            _ => return Err(io::Error::other("invalid fixture command")),
        }
        io::stdout().flush()?;
    }
    Err(io::Error::other(
        "fixture owner exited without confirming shutdown",
    ))
}
