//! Exercise the shipping Rust read lease on one fixed synthetic regular file.
#![forbid(unsafe_code)]
use safe_fs::Directory;
use std::ffi::OsStr;
use std::io::{self, BufRead, Read};
use std::path::Path;

fn run() -> io::Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [mode, root] = args.as_slice() else {
        return Err(io::Error::other("Expected read or hold and a fixture root"));
    };
    if std::env::var("IFW_QA_ISOLATED").as_deref() != Ok("1")
        || !matches!(mode.as_str(), "read" | "hold")
        || !(root == "/tmp/producer/source"
            || (root.starts_with("/run/user/0/doc/by-app/org.example.IfwServices/")
                && Path::new(root).file_name() == Some(OsStr::new("source"))))
    {
        return Err(io::Error::other("Expected the private Documents fixture"));
    }
    let dir = Directory::open_root(Path::new(root))?;
    let album = dir.open_directory(OsStr::new("album"))?;
    let mut file = album.open_file(OsStr::new("original.jpg"))?;
    let mut contents = Vec::new();
    (&mut file).take(64).read_to_end(&mut contents)?;
    if contents != b"Synthetic upload fixture\n" || !file.is_current_entry()? {
        return Err(io::Error::other("Unexpected synthetic regular file"));
    }
    println!("ACQUIRED identity={:?}", file.identity());
    if mode == "hold"
        && io::stdin().lock().lines().next().transpose()?.as_deref() != Some("release")
    {
        return Err(io::Error::other("Missing holder release"));
    }
    Ok(())
}

fn main() {
    if let Err(err) = run() {
        if let Some(n) = err.raw_os_error() {
            println!("REFUSED errno={n}");
            std::process::exit(20);
        }
        if err.kind() == io::ErrorKind::WouldBlock {
            // std::fs::TryLockError normalizes contention and can omit the native errno.
            println!("REFUSED kind=WouldBlock");
            std::process::exit(20);
        }
        eprintln!("{err}");
        std::process::exit(1);
    }
}
