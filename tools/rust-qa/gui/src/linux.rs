#[path = "linux_legacy.rs"]
mod legacy;

use super::{Command, Control};
use std::collections::HashMap;
use std::error::Error;
use std::ops::Deref;
use std::sync::atomic::Ordering;
use std::sync::mpsc::TrySendError;
use std::time::Duration;
use zbus::{
    Connection, connection::Builder, fdo, interface, object_server::SignalEmitter,
    zvariant::OwnedValue,
};

const NAME: &str = "org.example.IfwGuiProbe";
const INSTALLED_NAME: &str = "io.github.voltkraft.immich-folder-watch.RustAssessment";
const APP_PATH: &str = "/org/example/IfwGuiProbe";
const APP_INTERFACE: &str = "org.freedesktop.Application";
const WATCHER: &str = "org.kde.StatusNotifierWatcher";
const NO_DISPLAY: &str = "Graphics unavailable. Activate to retry. Background work continues.";
type PlatformData = HashMap<String, OwnedValue>;

struct Application {
    control: Control,
    admitted: bool,
    quitting: bool,
}
struct Item(Control, &'static str);

fn dispatch(control: &Control, command: Command) -> fdo::Result<()> {
    control.send(command).map_err(|error| match error {
        TrySendError::Full(_) => fdo::Error::LimitsExceeded("GUI command queue is full".into()),
        TrySendError::Disconnected(_) => fdo::Error::Failed("GUI command receiver closed".into()),
    })
}

impl Application {
    fn enqueue(&self, command: Command) -> fdo::Result<()> {
        if !self.admitted {
            return Err(fdo::Error::Failed("GUI startup has not completed".into()));
        }
        if self.quitting {
            return Err(fdo::Error::Failed("GUI is shutting down".into()));
        }
        dispatch(&self.control, command)
    }
}

#[interface(name = "org.freedesktop.Application")]
impl Application {
    fn activate(&self, _platform_data: PlatformData) -> fdo::Result<()> {
        self.enqueue(Command::Open)
    }

    fn activate_action(
        &mut self,
        action_name: &str,
        _parameter: Vec<OwnedValue>,
        _platform_data: PlatformData,
    ) -> fdo::Result<()> {
        let command = match action_name {
            "quit" => Command::Quit,
            "close" => Command::Close,
            "qa-destroy-graphics" if super::graphics::allows_test_fault() => {
                Command::DestroyGraphics
            }
            _ => return Err(fdo::Error::InvalidArgs("Unknown fixture action".into())),
        };
        self.enqueue(command)?;
        self.quitting = matches!(command, Command::Quit);
        Ok(())
    }
}

#[interface(name = "org.kde.StatusNotifierItem")]
impl Item {
    #[zbus(property)]
    fn id(&self) -> &str {
        self.1
    }
    #[zbus(property)]
    fn title(&self) -> &str {
        if self.0.graphics_attention.load(Ordering::Acquire) {
            NO_DISPLAY
        } else {
            "Desktop input probe"
        }
    }
    #[zbus(property)]
    fn status(&self) -> &str {
        if self.0.graphics_attention.load(Ordering::Acquire) {
            "NeedsAttention"
        } else {
            "Active"
        }
    }
    #[zbus(property)]
    fn category(&self) -> &str {
        "ApplicationStatus"
    }
    #[zbus(property)]
    fn icon_pixmap(&self) -> Vec<(i32, i32, &'static [u8])> {
        // The SNI interface carries straight-alpha ARGB32 bytes in network order.
        let mut pixels = include_bytes!("tray-icon.argb").as_slice();
        [16, 22, 32, 48, 64]
            .into_iter()
            .map(|size| {
                let (frame, rest) = pixels.split_at((size * size * 4) as usize);
                pixels = rest;
                (size, size, frame)
            })
            .collect()
    }
    #[zbus(signal)]
    async fn new_status(emitter: &SignalEmitter<'_>, status: &str) -> zbus::Result<()>;
    #[zbus(signal)]
    async fn new_title(emitter: &SignalEmitter<'_>) -> zbus::Result<()>;
    fn activate(&self, _x: i32, _y: i32) -> fdo::Result<()> {
        dispatch(&self.0, Command::Open)
    }
}

pub(super) fn graphics_attention(connection: &Connection, control: &Control, unavailable: bool) {
    if control
        .graphics_attention
        .swap(unavailable, Ordering::AcqRel)
        == unavailable
    {
        return;
    }
    let status = if unavailable {
        "NeedsAttention"
    } else {
        "Active"
    };
    let result = futures_lite::future::block_on(async {
        let emitter = SignalEmitter::new(connection, "/StatusNotifierItem")?;
        Item::new_status(&emitter, status).await?;
        Item::new_title(&emitter).await
    });
    if let Err(error) = result {
        println!("GRAPHICS_TRAY_STATUS {error}");
    }
}

pub(super) struct Primary {
    connection: Connection,
    installed_socket: Option<legacy::Guard>,
}

impl Deref for Primary {
    type Target = Connection;

    fn deref(&self) -> &Connection {
        &self.connection
    }
}

impl Primary {
    pub(super) async fn graceful_shutdown(self) {
        // The supervisor calls this after worker drain. Even a disconnected
        // object server cannot release the shipping endpoint earlier.
        self.connection.graceful_shutdown().await;
        drop(self.installed_socket);
    }
}

pub(super) fn start(control: Control) -> Result<Option<(Primary, bool)>, Box<dyn Error>> {
    if std::env::var("HOME").as_deref() != Ok("/tmp/home")
        || std::env::var("DBUS_SESSION_BUS_ADDRESS").as_deref() != Ok("unix:path=/tmp/session-bus")
    {
        return Err("Expected a private GUI assessment home and session bus".into());
    }
    let runtime = legacy::installed_runtime()?;
    let name = if runtime.is_some() {
        INSTALLED_NAME
    } else {
        NAME
    };
    futures_lite::future::block_on(async {
        let connection = Builder::session()?
            .serve_at(
                APP_PATH,
                Application {
                    control: control.clone(),
                    admitted: false,
                    quitting: false,
                },
            )?
            .method_timeout(Duration::from_secs(2))
            .build()
            .await?;
        // Hold the async interface lock through both elections. An ordinary
        // simultaneous D-Bus Activate waits until admission has succeeded or failed.
        let application = connection
            .object_server()
            .interface::<_, Application>(APP_PATH)
            .await?;
        let mut admission = application.get_mut().await;
        let installed_socket = match connection
            .request_name_with_flags(name, fdo::RequestNameFlags::DoNotQueue.into())
            .await
        {
            Ok(fdo::RequestNameReply::PrimaryOwner) => {
                runtime.map(legacy::Runtime::claim).transpose()?
            }
            Err(zbus::Error::NameTaken) => {
                let owner = fdo::DBusProxy::new(&connection)
                    .await?
                    .get_name_owner(name.try_into()?)
                    .await?;
                // A unique destination cannot autostart or silently target a successor.
                let reply = connection
                    .call_method(
                        Some(owner.as_str()),
                        APP_PATH,
                        Some(APP_INTERFACE),
                        "Activate",
                        &PlatformData::new(),
                    )
                    .await?;
                if reply.header().sender().map(|name| name.as_str()) != Some(owner.as_str())
                    || !reply.body().is_empty()
                {
                    return Err("Unexpected reply from the running GUI".into());
                }
                println!("SECONDARY_ACTIVATED owner={owner}");
                return Ok(None);
            }
            Err(error) => return Err(error.into()),
            Ok(_) => return Err("Unexpected D-Bus ownership result for a new connection".into()),
        };
        connection
            .object_server()
            .at("/StatusNotifierItem", Item(control, name))
            .await?;
        admission.admitted = true;
        drop(admission);
        drop(application);
        let result = connection
            .call_method(
                Some(WATCHER),
                "/StatusNotifierWatcher",
                Some(WATCHER),
                "RegisterStatusNotifierItem",
                &name,
            )
            .await;
        if let Err(error) = &result {
            println!("TRAY_REGISTRATION {error}");
        }
        Ok(Some((
            Primary {
                connection,
                installed_socket,
            },
            result.is_ok(),
        )))
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc::sync_channel;

    #[test]
    fn secondary_activation_reports_full_closed_and_quitting_queues() {
        let (sender, commands) = sync_channel(1);
        let mut app = Application {
            control: Control {
                sender,
                window: Default::default(),
                graphics_attention: Default::default(),
                appearance: Default::default(),
            },
            admitted: false,
            quitting: false,
        };
        assert!(matches!(
            app.activate(PlatformData::new()),
            Err(fdo::Error::Failed(_))
        ));
        app.admitted = true;
        app.activate(PlatformData::new()).unwrap();
        assert!(matches!(
            app.activate(PlatformData::new()),
            Err(fdo::Error::LimitsExceeded(_))
        ));
        assert!(matches!(
            app.activate_action("quit", vec![], PlatformData::new()),
            Err(fdo::Error::LimitsExceeded(_))
        ));
        assert!(matches!(commands.try_recv(), Ok(Command::Open)));
        app.activate_action("quit", vec![], PlatformData::new())
            .unwrap();
        assert!(matches!(commands.try_recv(), Ok(Command::Quit)));
        assert!(matches!(
            app.activate(PlatformData::new()),
            Err(fdo::Error::Failed(_))
        ));
        drop(commands);
        assert!(matches!(
            dispatch(&app.control, Command::Open),
            Err(fdo::Error::Failed(_))
        ));
    }
}
