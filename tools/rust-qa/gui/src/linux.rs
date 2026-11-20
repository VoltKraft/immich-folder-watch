use super::{Command, Control};
use std::collections::HashMap;
use std::error::Error;
use std::time::Duration;
use zbus::{Connection, connection::Builder, fdo, interface, zvariant::OwnedValue};

const NAME: &str = "org.example.IfwGuiProbe";
const WATCHER: &str = "org.kde.StatusNotifierWatcher";
type PlatformData = HashMap<String, OwnedValue>;

struct Application(Control);
struct Item(Control);

fn dispatch(control: &Control, command: Command) -> fdo::Result<()> {
    control
        .send(command)
        .map_err(|_| fdo::Error::Failed("GUI command queue unavailable".into()))
}

#[interface(name = "org.freedesktop.Application")]
impl Application {
    fn activate(&self, _platform_data: PlatformData) -> fdo::Result<()> {
        dispatch(&self.0, Command::Open)
    }

    fn activate_action(
        &self,
        action_name: &str,
        _parameter: Vec<OwnedValue>,
        _platform_data: PlatformData,
    ) -> fdo::Result<()> {
        match action_name {
            "quit" => dispatch(&self.0, Command::Quit),
            "close" => dispatch(&self.0, Command::Close),
            _ => Err(fdo::Error::InvalidArgs("Unknown fixture action".into())),
        }
    }
}

// The synthetic watcher exercises registration, item discovery and its primary activation.
#[interface(name = "org.kde.StatusNotifierItem")]
impl Item {
    #[zbus(property)]
    fn id(&self) -> &str {
        NAME
    }
    #[zbus(property)]
    fn title(&self) -> &str {
        "Desktop input probe"
    }
    #[zbus(property)]
    fn status(&self) -> &str {
        "Active"
    }
    #[zbus(property)]
    fn category(&self) -> &str {
        "ApplicationStatus"
    }
    fn activate(&self, _x: i32, _y: i32) -> fdo::Result<()> {
        dispatch(&self.0, Command::Open)
    }
}

pub(super) fn start(control: Control) -> Result<(Connection, bool), Box<dyn Error>> {
    if std::env::var("HOME").as_deref() != Ok("/tmp/home")
        || std::env::var("DBUS_SESSION_BUS_ADDRESS").as_deref() != Ok("unix:path=/tmp/session-bus")
    {
        return Err("Expected a private GUI assessment home and session bus".into());
    }
    futures_lite::future::block_on(async {
        let connection = Builder::session()?
            .name(NAME)?
            .serve_at("/org/example/IfwGuiProbe", Application(control.clone()))?
            .serve_at("/StatusNotifierItem", Item(control))?
            .method_timeout(Duration::from_secs(3))
            .build()
            .await?;
        let result = connection
            .call_method(
                Some(WATCHER),
                "/StatusNotifierWatcher",
                Some(WATCHER),
                "RegisterStatusNotifierItem",
                &NAME,
            )
            .await;
        if let Err(error) = &result {
            println!("TRAY_REGISTRATION {error}");
        }
        Ok((connection, result.is_ok()))
    })
}
