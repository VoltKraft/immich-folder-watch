// Compiled with the source-bound inventory, YAML model and budgets of the Linux comparison.
static WINDOWS_ENDPOINT: std::sync::OnceLock<SocketAddr> = std::sync::OnceLock::new();

struct WindowsInput {
    config: safe_fs::VerifiedFile,
    media: Directory,
    media_path: PathBuf,
    api_url: String,
}

fn windows_input() -> Result<WindowsInput, Box<dyn Error>> {
    use std::ffi::OsStr;
    let value = |name: &str| std::env::var(name);
    if value("IFW_QA_ISOLATED").as_deref() != Ok("1")
        || value("IFW_QA_BENCHMARK").as_deref() != Ok("1")
    {
        return Err("A disposable native Windows inventory run is required".into());
    }
    let local = value("IFW_QA_LOCAL_WINDOWS").as_deref() == Ok("1");
    let temp_key = if local {
        // The supervisor authenticated the native computer and user before starting this worker.
        // Preserve the worker's safe-code boundary and independently bind its directory and token below.
        if !cfg!(target_arch = "x86_64")
            || std::env::var_os("GITHUB_ACTIONS").is_some()
            || std::env::var_os("RUNNER_ENVIRONMENT").is_some()
            || !value("COMPUTERNAME")?.eq_ignore_ascii_case("IFW-QA25")
            || !value("USERNAME")?.eq_ignore_ascii_case("ifw-test")
        {
            return Err("Unexpected local inventory host".into());
        }
        "IFW_QA_LOCAL_TEMP"
    } else {
        if value("GITHUB_ACTIONS").as_deref() != Ok("true")
            || value("RUNNER_ENVIRONMENT").as_deref() != Ok("github-hosted")
            || value("RUNNER_OS").as_deref() != Ok("Windows")
        {
            return Err("Unexpected native inventory host".into());
        }
        "RUNNER_TEMP"
    };
    let runner = PathBuf::from(value(temp_key)?);
    let top = PathBuf::from(value("IFW_QA_INVENTORY_ROOT")?);
    let name = top.file_name().ok_or("Missing private inventory root")?;
    let token = value("IFW_QA_INVENTORY_TOKEN")?;
    if !runner.is_absolute()
        || top.parent() != Some(runner.as_path())
        || !name.to_string_lossy().starts_with("ifw-rw02-")
        || token.len() != 32
        || !token.bytes().all(|b| b.is_ascii_hexdigit())
    {
        return Err("Expected a directly owned runner temporary directory".into());
    }
    let base = Directory::open_root(&runner)?.open_directory(name)?;
    let mut owner = String::new();
    base.open_file(OsStr::new("inventory.owner"))?
        .take(33)
        .read_to_string(&mut owner)?;
    if owner != token {
        return Err("Inventory ownership marker did not match".into());
    }
    let trial = value("IFW_QA_INVENTORY_TRIAL")?;
    if !matches!(
        trial.as_str(),
        "rust-1" | "rust-2" | "rust-3" | "rust-1-scan" | "rust-2-scan" | "rust-3-scan"
    ) {
        return Err("Unexpected private inventory trial".into());
    }
    let folder = base.open_directory(OsStr::new(&trial))?;
    let config = folder.open_file(OsStr::new("config.yaml"))?;
    let (media, media_path) = if trial.ends_with("-scan") {
        (base.open_directory(OsStr::new("files"))?, top.join("files"))
    } else {
        (
            folder.open_directory(OsStr::new("empty"))?,
            top.join(trial).join("empty"),
        )
    };
    let port: u16 = value("IFW_QA_INVENTORY_PORT")?.parse()?;
    if port < 1024 {
        return Err("Expected the recorder's exclusive ephemeral loopback port".into());
    }
    let endpoint = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    WINDOWS_ENDPOINT
        .set(endpoint)
        .map_err(|_| "Duplicate inventory endpoint")?;
    Ok(WindowsInput {
        config,
        media,
        media_path,
        api_url: format!("http://{endpoint}/api"),
    })
}

fn inventory_release() -> Result<(), Box<dyn Error>> {
    let mut start = [0_u8];
    io::stdin().read_exact(&mut start)?;
    if start != *b"S" {
        return Err("Invalid private inventory bootstrap".into());
    }
    Ok(())
}
