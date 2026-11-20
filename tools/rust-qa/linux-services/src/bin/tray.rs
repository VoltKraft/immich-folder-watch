//! Isolated registration and activation adapter for a private Linux desktop.
#![forbid(unsafe_code)]

use desktop_lifecycle::{DesktopLifecycle, HostCommand};
use futures_lite::{StreamExt, future};
use std::collections::HashMap;
use std::error::Error;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use zbus::{Connection, connection::Builder, fdo, interface, zvariant::OwnedValue};

const NAME: &str = "org.example.IfwServices";
const WATCHER: &str = "org.kde.StatusNotifierWatcher";
const GUI: &str = "org.example.IfwGuiProbe";
const APP: &str = "org.freedesktop.Application";
type Data = HashMap<String, OwnedValue>;

struct State {
    lifecycle: DesktopLifecycle,
    registered: Option<String>,
}

#[derive(Clone)]
struct Control {
    state: Arc<Mutex<State>>,
    quit: async_channel::Sender<()>,
}

impl Control {
    async fn forward(bus: &Connection, action: &str) -> fdo::Result<()> {
        // The assessment keeps the already measured GUI backend in a separate native process.
        let result = if action == "open" {
            bus.call_method(
                Some(GUI),
                "/org/example/IfwGuiProbe",
                Some(APP),
                "Activate",
                &Data::new(),
            )
            .await
        } else {
            bus.call_method(
                Some(GUI),
                "/org/example/IfwGuiProbe",
                Some(APP),
                "ActivateAction",
                &(action, Vec::<OwnedValue>::new(), Data::new()),
            )
            .await
        };
        result
            .map(|_| ())
            .map_err(|err| fdo::Error::Failed(err.to_string()))
    }

    async fn open(&self, bus: &Connection) -> fdo::Result<()> {
        Self::forward(bus, "open").await?;
        self.state
            .lock()
            .expect("lifecycle mutex poisoned")
            .lifecycle
            .activate();
        Ok(())
    }

    async fn availability(&self, bus: &Connection, owner: Option<String>) -> zbus::Result<()> {
        let reveal = {
            let mut state = self.state.lock().expect("lifecycle mutex poisoned");
            state.registered = owner;
            let available = state.registered.is_some();
            state.lifecycle.tray_result(available) == Some(HostCommand::ShowAndFocus)
        };
        if reveal {
            Self::forward(bus, "open").await?;
        }
        Ok(())
    }
}

struct Application(Control);
#[interface(name = "org.freedesktop.Application")]
impl Application {
    async fn activate(&self, _data: Data, #[zbus(connection)] bus: &Connection) -> fdo::Result<()> {
        self.0.open(bus).await
    }
    async fn activate_action(
        &self,
        name: &str,
        _args: Vec<OwnedValue>,
        _data: Data,
        #[zbus(connection)] bus: &Connection,
    ) -> fdo::Result<()> {
        if !matches!(name, "close" | "quit") {
            return Err(fdo::Error::InvalidArgs("Unsupported action".into()));
        }
        Control::forward(bus, name).await?;
        let mut model = self.0.state.lock().expect("lifecycle mutex poisoned");
        if name == "close" {
            model.lifecycle.close_window();
        } else {
            model.lifecycle.request_quit();
            let _ = self.0.quit.try_send(());
        }
        Ok(())
    }
}

struct Item(Control);
#[interface(name = "org.kde.StatusNotifierItem")]
impl Item {
    #[zbus(property)]
    fn id(&self) -> &str {
        NAME
    }
    #[zbus(property)]
    fn status(&self) -> &str {
        "Active"
    }
    #[zbus(property)]
    fn title(&self) -> &str {
        "Native service assessment"
    }
    #[zbus(property)]
    fn category(&self) -> &str {
        "ApplicationStatus"
    }
    async fn activate(
        &self,
        _x: i32,
        _y: i32,
        #[zbus(connection)] bus: &Connection,
    ) -> fdo::Result<()> {
        self.0.open(bus).await
    }
}

struct Observation(Control);
#[interface(name = "org.example.IfwServices.Observation")]
impl Observation {
    fn state(&self) -> (String, String, String) {
        let state = self.0.state.lock().expect("lifecycle mutex poisoned");
        (
            format!("{:?}", state.lifecycle.window_intent()),
            format!("{:?}", state.lifecycle.tray()),
            state.registered.clone().unwrap_or_default(),
        )
    }
}

async fn current_owner(bus: &fdo::DBusProxy<'_>) -> zbus::Result<Option<String>> {
    match bus.get_name_owner(WATCHER.try_into()?).await {
        Ok(name) => Ok(Some(name.to_string())),
        Err(fdo::Error::NameHasNoOwner(_)) => Ok(None),
        Err(error) => Err(error.into()),
    }
}

async fn watch(connection: &Connection, control: &Control) -> zbus::Result<()> {
    let bus = fdo::DBusProxy::new(connection).await?;
    let mut changes = bus
        .receive_name_owner_changed_with_args(&[(0, WATCHER)])
        .await?
        .map(|event| {
            event
                .args()
                .map(|args| args.new_owner().as_ref().map(ToString::to_string))
        });
    let mut owner = current_owner(&bus).await?;
    loop {
        if let Some(unique) = &owner {
            // A replacement can take over during RegisterStatusNotifierItem. Send only to
            // the observed unique name and invalidate an outstanding call as soon as ownership changes.
            let registration = async {
                let reply = connection
                    .call_method(
                        Some(unique.as_str()),
                        "/StatusNotifierWatcher",
                        Some(WATCHER),
                        "RegisterStatusNotifierItem",
                        &NAME,
                    )
                    .await;
                if let Err(err) = &reply {
                    println!("Registration refused by {unique}: {err}");
                }
                Ok::<_, zbus::Error>(Some(reply.is_ok()))
            };
            let registered = future::or(
                async {
                    changes
                        .next()
                        .await
                        .ok_or_else(|| zbus::Error::Failure("Watcher stream closed".into()))??;
                    Ok(None)
                },
                registration,
            )
            .await?;
            let confirmed = current_owner(&bus).await?;
            if registered.is_none() || confirmed != owner {
                // An initial response may still be pending. Preserve background intent until
                // a current watcher accepts/refuses registration or the name is actually absent.
                if control
                    .state
                    .lock()
                    .expect("lifecycle mutex poisoned")
                    .registered
                    .is_some()
                {
                    control.availability(connection, None).await?;
                }
                owner = confirmed;
                continue;
            }
            control
                .availability(
                    connection,
                    if registered == Some(true) {
                        owner.clone()
                    } else {
                        None
                    },
                )
                .await?;
        } else {
            control.availability(connection, None).await?;
        }
        let Some(changed) = changes.next().await else {
            return Err(zbus::Error::Failure("Watcher stream closed".into()));
        };
        let next = changed?;
        if next != owner && owner.is_some() {
            control.availability(connection, None).await?;
        }
        // Older signals can already be queued after the initial GetNameOwner snapshot.
        owner = current_owner(&bus).await?;
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    if std::env::var("IFW_QA_ISOLATED").as_deref() != Ok("1")
        || std::env::var("DBUS_SESSION_BUS_ADDRESS").as_deref() != Ok("unix:path=/tmp/session-bus")
    {
        return Err("Use a private assessment session".into());
    }
    future::block_on(async {
        let (quit, stopped) = async_channel::bounded(1);
        let control = Control {
            state: Arc::new(Mutex::new(State {
                lifecycle: DesktopLifecycle::new(true),
                registered: None,
            })),
            quit,
        };
        let connection = Builder::session()?
            .name(NAME)?
            .serve_at("/org/example/IfwServices", Application(control.clone()))?
            .serve_at("/org/example/IfwServices", Observation(control.clone()))?
            .serve_at("/StatusNotifierItem", Item(control.clone()))?
            .method_timeout(Duration::from_secs(2))
            .build()
            .await?;
        let result = future::or(
            async {
                let _ = stopped.recv().await;
                Ok(())
            },
            watch(&connection, &control),
        )
        .await;
        connection.graceful_shutdown().await;
        result?;
        if control
            .state
            .lock()
            .expect("lifecycle mutex poisoned")
            .lifecycle
            .background_stopped()
            != Some(HostCommand::ExitEventLoop)
        {
            return Err("Unexpected shutdown state".into());
        }
        println!("DRAINED");
        Ok(())
    })
}
