//! Print the resolved startup language and the kind of synthetic config read for the C# comparison.
#[cfg(target_os = "linux")]
fn main() {
    use ifw_yaml_assessment::startup_language::{self, Language, Preference};
    let code = |language| match language {
        Language::English => "en",
        Language::German => "de",
    };
    let startup = startup_language::load();
    let (read, setting) = match startup.preference {
        Ok(Some(Preference::Explicit(language))) => ("loaded", code(language)),
        Ok(Some(Preference::System)) => ("loaded", "auto"),
        Ok(None) => ("missing", "auto"),
        Err(_) => ("failed", "auto"),
    };
    println!(
        "{}",
        serde_json::json!({
            "path": startup_language::config_path().ok(), "read": read,
        "setting": setting, "language": code(startup.language),
        "systemLanguage": code(Preference::System.resolve(startup.system)),
        })
    );
}

#[cfg(not(target_os = "linux"))]
fn main() {
    eprintln!("The XDG startup language example requires Linux");
    std::process::exit(2);
}
