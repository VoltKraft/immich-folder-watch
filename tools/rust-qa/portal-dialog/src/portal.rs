//! Development client for the real GTK portal frontend, request signals and notification relay.
#![forbid(unsafe_code)]

use futures_lite::{StreamExt, future};
use std::collections::HashMap;
use std::error::Error;
use std::path::{Path, PathBuf};
use std::time::Duration;
use zbus::{
    Connection, MatchRule, MessageStream,
    connection::Builder,
    fdo,
    message::Type,
    zvariant::{OwnedObjectPath, OwnedValue, Value},
};

const DESKTOP: &str = "org.freedesktop.portal.Desktop";
const OBJECT: &str = "/org/freedesktop/portal/desktop";
const REQUEST: &str = "org.freedesktop.portal.Request";
pub const APP: &str = "org.example.IfwPortalDialog";
type Options<'a> = HashMap<&'a str, Value<'a>>;
type Failure = Box<dyn Error>;

pub(crate) fn documents_mount() -> Result<PathBuf, Failure> {
    let mount = PathBuf::from(std::env::var_os("XDG_RUNTIME_DIR").ok_or("No application runtime")?)
        .join("doc");
    let mounted = mount.canonicalize()?;
    let mounts = std::fs::read_to_string("/proc/self/mountinfo")?;
    let visible: Vec<_> = mounts
        .lines()
        .filter(|row| row.contains(" - fuse.portal "))
        .collect();
    println!("DOCUMENT_MOUNT {} {visible:?}", mounted.display());
    if !visible
        .iter()
        .any(|row| row.split_whitespace().nth(4) == mounted.to_str())
    {
        return Err("Returned application directory has no Documents FUSE mount".into());
    }
    Ok(mount)
}

pub(crate) fn inspect_grant(uri: &str) -> Result<(), Failure> {
    let grant = crate::document_uri::parse(uri, &documents_mount()?)?;
    let root = safe_fs::Directory::open_root(&grant.path)?;
    let entries = root.entries(8)?;
    if entries.len() != 1 || entries[0].kind != safe_fs::EntryKind::File {
        return Err("Portal directory does not contain the expected synthetic entry".into());
    }
    println!("DOCUMENT_ENTRY {}", entries[0].name.to_string_lossy());
    println!(
        "DOCUMENT_GRANT {} {}",
        grant.id.to_string_lossy(),
        grant.path.display()
    );
    Ok(())
}

async fn request(bus: &Connection, parent: &str, action: &str) -> Result<(), Failure> {
    let background = matches!(action, "background" | "background-off");
    let daemon = fdo::DBusProxy::new(bus)
        .await?
        .get_name_owner(DESKTOP.try_into()?)
        .await?;
    let token = format!("assessment_{}", std::process::id());
    let sender = bus.unique_name().ok_or("No private D-Bus unique name")?;
    let sender = sender.as_str().trim_start_matches(':').replace('.', "_");
    let expected = format!("{OBJECT}/request/{sender}/{token}");
    let rule = MatchRule::builder()
        .msg_type(Type::Signal)
        .sender(daemon.as_str())?
        .path(expected.as_str())?
        .interface(REQUEST)?
        .member("Response")?
        .build();
    let mut responses = MessageStream::for_match_rule(rule, bus, Some(4)).await?;
    let mut options = Options::new();
    options.insert("handle_token", Value::from(token.as_str()));
    let result = if background {
        options.insert(
            "reason",
            Value::from("Synthetic autostart capability assessment"),
        );
        options.insert("autostart", Value::from(action == "background"));
        options.insert(
            "commandline",
            Value::from(vec!["portal-dialog-assessment", "notify"]),
        );
        bus.call_method(
            Some(daemon.as_str()),
            OBJECT,
            Some("org.freedesktop.portal.Background"),
            "RequestBackground",
            &(parent, &options),
        )
        .await
    } else {
        options.insert("directory", Value::from(true));
        options.insert("multiple", Value::from(false));
        if let Some(folder) = selection_folder(action) {
            options.insert(
                "current_folder",
                Value::from(std::ffi::CString::new(folder)?.into_bytes_with_nul()),
            );
            options.insert("accept_label", Value::from("_Use folder"));
        }
        bus.call_method(
            Some(daemon.as_str()),
            OBJECT,
            Some("org.freedesktop.portal.FileChooser"),
            "OpenFile",
            &(parent, "Select a synthetic watch folder", &options),
        )
        .await
    };
    let reply = match result {
        Err(zbus::Error::MethodError(name, _, _))
            if background
                && matches!(
                    name.as_str(),
                    "org.freedesktop.DBus.Error.UnknownMethod"
                        | "org.freedesktop.DBus.Error.UnknownInterface"
                        | "org.freedesktop.portal.Error.NotAllowed"
                        | "org.freedesktop.DBus.Error.AccessDenied"
                ) =>
        {
            println!("BACKGROUND_UNAVAILABLE {name}");
            return Ok(());
        }
        other => other?,
    };
    let handle: OwnedObjectPath = reply.body().deserialize()?;
    if handle.as_str() != expected {
        return Err("Portal returned another request handle".into());
    }
    println!("REQUEST {handle}");
    let response = future::or(
        async { responses.next().await.transpose().map_err(Failure::from) },
        async {
            async_io::Timer::after(Duration::from_secs(8)).await;
            Ok(None)
        },
    )
    .await?;
    let Some(response) = response else {
        let _ = bus
            .call_method(
                Some(daemon.as_str()),
                handle.as_str(),
                Some(REQUEST),
                "Close",
                &(),
            )
            .await;
        return Err("Portal request timed out".into());
    };
    let (code, mut results): (u32, HashMap<String, OwnedValue>) = response.body().deserialize()?;
    if background {
        let enabled = results
            .get("autostart")
            .map(bool::try_from)
            .transpose()?
            .unwrap_or(false);
        let allowed = results
            .get("background")
            .map(bool::try_from)
            .transpose()?
            .unwrap_or(false);
        println!("BACKGROUND code={code} background={allowed} autostart={enabled}");
    } else {
        let uris: Vec<String> = results
            .remove("uris")
            .map(Vec::<String>::try_from)
            .transpose()?
            .unwrap_or_default();
        println!("CHOOSER_RESPONSE code={code} uri_count={}", uris.len());
        if selection_folder(action).is_some() {
            if code != 0 {
                return Err(
                    format!("Expected accepted folder chooser, got response {code}").into(),
                );
            }
            if uris.len() != 1 {
                return Err("Unexpected number of selected URIs".into());
            }
            println!("CHOOSER_SELECTED {}", uris[0]);
            if Path::new("/.flatpak-info").is_file() {
                inspect_grant(&uris[0])?;
            }
            return Ok(());
        }
        if code != 1 || !uris.is_empty() {
            return Err("Expected a cancelled folder request without grants".into());
        }
        println!("CHOOSER_CANCELLED");
    }
    Ok(())
}

fn selection_folder(action: &str) -> Option<&'static str> {
    match action {
        "select" => Some("/tmp/selection/album"),
        "select-escaped" => Some("/tmp/selection/Grüße #2 %2F"),
        _ => None,
    }
}

pub async fn run(action: &str, parent: &str) -> Result<(), Failure> {
    let installed = Path::new("/.flatpak-info").is_file();
    let chooser_only = action.strip_prefix("unregistered-host-");
    if chooser_only
        .is_some_and(|name| installed || (name != "cancel" && selection_folder(name).is_none()))
    {
        return Err("The unregistered host mode accepts only FileChooser actions".into());
    }
    let action = chooser_only.unwrap_or(action);
    let bus = Builder::session()?
        .method_timeout(Duration::from_secs(4))
        .build()
        .await?;
    if chooser_only.is_some() {
        println!("CHOOSER_UNREGISTERED_HOST");
    } else if !installed {
        bus.call_method(
            Some(DESKTOP),
            OBJECT,
            Some("org.freedesktop.host.portal.Registry"),
            "Register",
            &(APP, Options::new()),
        )
        .await?;
    }
    match action {
        "cancel" | "select" | "select-escaped" | "background" | "background-off" => {
            request(&bus, parent, action).await?
        }
        "notify" => {
            let message = Options::from([
                ("title", Value::from("Synthetic notification")),
                ("body", Value::from("Private portal delivery test")),
            ]);
            let interface = "org.freedesktop.portal.Notification";
            bus.call_method(
                Some(DESKTOP),
                OBJECT,
                Some(interface),
                "AddNotification",
                &("native-test", message),
            )
            .await?;
            println!("NOTIFICATION_ACCEPTED");
        }
        "withdraw" => {
            bus.call_method(
                Some(DESKTOP),
                OBJECT,
                Some("org.freedesktop.portal.Notification"),
                "RemoveNotification",
                &"native-test",
            )
            .await?;
            println!("NOTIFICATION_WITHDRAWN");
        }
        _ => return Err("Expected chooser, background, notify or withdraw".into()),
    }
    bus.graceful_shutdown().await;
    Ok(())
}
