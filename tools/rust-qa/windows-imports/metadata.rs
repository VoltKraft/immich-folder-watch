//! Read WinMD signatures using the same Microsoft reader as the import generator.

fn main() {
    for (library, functions) in lib::libraries() {
        for (name, convention) in functions {
            let size = match convention {
                lib::CallingConvention::Stdcall(bytes) => bytes.to_string(),
                lib::CallingConvention::Cdecl => "cdecl".into(),
            };
            println!("{library}\t{name}\t{size}");
        }
    }
}
