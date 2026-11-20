//! Own the optional Linux comparison worker for this development fixture.
use std::io;
use std::process::{Child, Command, Stdio};

pub(super) struct Benchmark(Option<Child>);

impl Benchmark {
    pub(super) fn start() -> io::Result<Self> {
        let active = std::env::var("IFW_QA_BENCHMARK").as_deref() == Ok("1");
        let child = if active {
            Some(
                Command::new("/app/ifw-performance-worker")
                    .stdin(Stdio::piped())
                    .spawn()?,
            )
        } else {
            None
        };
        Ok(Self(child))
    }

    pub(super) fn finish(mut self) -> io::Result<()> {
        if let Some(mut child) = self.0.take() {
            drop(child.stdin.take());
            if !child.wait()?.success() {
                return Err(io::Error::other("Comparison worker failed"));
            }
        }
        Ok(())
    }
}
