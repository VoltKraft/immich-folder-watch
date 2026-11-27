use super::{SIGNAL, TIMEOUT, announce};
use std::io::{self, Read};
use std::path::Path;

#[path = "../gui/src/win32_instance.rs"]
mod local;

pub fn check_environment(_: &Path, owner: &str, role: &str) -> io::Result<()> {
    let isolated_writer =
        role == "writer" && std::env::var("IFW_QA_EXISTING_SESSION").as_deref() == Ok("1");
    if !isolated_writer
        && ![
            ("RUNNER_ENVIRONMENT", "github-hosted"),
            ("GITHUB_ACTIONS", "true"),
            ("GITHUB_REPOSITORY", "VoltKraft/immich-folder-watch"),
            ("GITHUB_REF", "refs/heads/rewrite/rust"),
        ]
        .iter()
        .all(|(key, value)| std::env::var(key).as_deref() == Ok(*value))
    {
        return Err(io::Error::other(
            "the legacy IPC names require the rewrite branch's disposable Windows runner",
        ));
    }
    if !local::valid_sid(owner) {
        return Err(io::Error::other(
            "invalid account SID from the development oracle",
        ));
    }
    Ok(())
}

fn mutex_name(sid: &str) -> String {
    format!(r"Local\ImmichFolderWatch-{sid}")
}
fn pipe_name(sid: &str) -> String {
    format!(r"\\.\pipe\ifw-{sid}")
}

pub fn signal(_: &Path, sid: &str, peer: u32) -> io::Result<()> {
    let (_mutex, created) = local::mutex(&mutex_name(sid), None)?;
    if created {
        return Err(io::Error::other("expected an existing legacy mutex"));
    }
    local::send(&local::connect(&pipe_name(sid), TIMEOUT)?, peer, SIGNAL)?;
    announce("SECONDARY_SIGNALLED")
}

pub fn listen(_: &Path, sid: &str, peer: u32) -> io::Result<()> {
    let (_mutex, created) = local::mutex(&mutex_name(sid), Some(sid))?;
    if !created {
        return Err(io::Error::other("an existing owner holds the legacy mutex"));
    }
    let pipe = local::inbound(&pipe_name(sid), sid)?;
    announce("PRIMARY_READY")?;
    local::accept(&pipe)?;
    if local::peer_pid(&pipe, false)? != peer {
        return Err(io::Error::other("unexpected local activation peer"));
    }
    let mut bytes = Vec::new();
    let result = pipe.take(65).read_to_end(&mut bytes);
    if let Err(error) = result
        && error.kind() != io::ErrorKind::BrokenPipe
    {
        return Err(error);
    }
    if bytes != SIGNAL {
        return Err(io::ErrorKind::InvalidData.into());
    }
    announce("SHOW_GUI")
}
