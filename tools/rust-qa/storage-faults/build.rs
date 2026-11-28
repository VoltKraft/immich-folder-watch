//! Append test visibility wrappers to unchanged reviewed development source.

use std::{env, fs, path::PathBuf};

fn main() {
    let sources = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap()).join("../storage/src");
    let output = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    for name in ["preflight.rs", "wal_preflight_cases.rs"] {
        let source = sources.join(name);
        println!("cargo:rerun-if-changed={}", source.display());
        fs::copy(source, output.join(name)).unwrap();
    }
    let source = sources.join("main.rs");
    println!("cargo:rerun-if-changed={}", source.display());
    let mut bytes = fs::read(&source).unwrap();
    bytes.extend_from_slice(
        br#"
pub(super) fn fault_snapshot(database: &Connection) -> Result<Value> {
    snapshot(database)
}
pub(super) fn fault_open_existing(database: &Path, scratch: &Path) -> Result<Connection> {
    preflight::open_existing(database, scratch)
}
"#,
    );
    let module = output.join("reviewed-storage.rs");
    fs::write(&module, bytes).unwrap();
    fs::write(
        output.join("reviewed-module.rs"),
        format!("#[allow(dead_code)]\n#[path = {module:?}]\nmod reviewed;\n"),
    )
    .unwrap();
}
