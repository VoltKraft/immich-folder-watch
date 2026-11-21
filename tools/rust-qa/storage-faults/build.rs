//! Append test visibility wrappers to unchanged reviewed development source.

use std::{env, fs, path::PathBuf};

fn main() {
    let source =
        PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap()).join("../storage/src/main.rs");
    println!("cargo:rerun-if-changed={}", source.display());
    let output = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let mut bytes = fs::read(&source).unwrap();
    bytes.extend_from_slice(
        br#"
pub(super) fn fault_snapshot(database: &Connection) -> Result<Value> {
    snapshot(database)
}
pub(super) fn fault_initialize_wal(database: &Connection) -> Result<()> {
    initialize_wal(database)
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
