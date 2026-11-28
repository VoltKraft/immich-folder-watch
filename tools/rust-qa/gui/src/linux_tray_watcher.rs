//! Keep the primary's advertised tray availability tied to the real watcher owner.
use super::{Command, Control, WATCHER};
use futures_lite::{StreamExt, future};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};
use zbus::{Connection, Task, fdo};

pub(super) struct Watcher {
    pub(super) available: Arc<AtomicBool>,
    _observer: Option<Task<()>>,
}

enum Registration {
    Changed,
    Observed(bool),
}

async fn current_owner(bus: &fdo::DBusProxy<'_>) -> zbus::Result<Option<String>> {
    match bus.get_name_owner(WATCHER.try_into()?).await {
        Ok(owner) => Ok(Some(owner.to_string())),
        Err(fdo::Error::NameHasNoOwner(_)) => Ok(None),
        Err(error) => Err(error.into()),
    }
}

async fn owner_change(changes: &mut fdo::NameOwnerChangedStream) -> zbus::Result<()> {
    let event = changes
        .next()
        .await
        .ok_or_else(|| zbus::Error::Failure("Watcher stream closed".into()))?;
    let args = event.args()?;
    println!(
        "TRAY_OWNER old={} new={}",
        args.old_owner().as_ref().map_or("none", |n| n.as_str()),
        args.new_owner().as_ref().map_or("none", |n| n.as_str())
    );
    Ok(())
}

fn accepted(
    expected: &str,
    sender: Option<&str>,
    empty_reply: bool,
    current: Option<&str>,
) -> bool {
    empty_reply && sender == Some(expected) && current == Some(expected)
}

async fn register(
    connection: &Connection,
    bus: &fdo::DBusProxy<'_>,
    changes: &mut fdo::NameOwnerChangedStream,
    item_name: &str,
) -> zbus::Result<Registration> {
    future::or(
        async {
            owner_change(changes).await?;
            Ok(Registration::Changed)
        },
        async {
            let Some(owner) = current_owner(bus).await? else {
                return Ok(Registration::Observed(false));
            };
            // Send to the unique owner. A name transition while the RPC or either
            // ownership query is in flight invalidates even a later successful reply.
            let result = connection
                .call_method(
                    Some(owner.as_str()),
                    "/StatusNotifierWatcher",
                    Some(WATCHER),
                    "RegisterStatusNotifierItem",
                    &item_name,
                )
                .await;
            let current = current_owner(bus).await?;
            if current.as_ref() != Some(&owner) {
                return Ok(Registration::Changed);
            }
            let available = match result {
                Ok(reply) => accepted(
                    &owner,
                    reply.header().sender().map(|s| s.as_str()),
                    reply.body().is_empty(),
                    current.as_deref(),
                ),
                Err(error) => {
                    eprintln!("Tray registration with {owner} failed: {error}");
                    false
                }
            };
            println!(
                "TRAY_REGISTRATION owner={owner} confirmed={} available={available}",
                current.as_deref().unwrap_or("none")
            );
            Ok(Registration::Observed(available))
        },
    )
    .await
}

fn publish(available: &AtomicBool, control: &Control, next: bool) {
    if available.swap(next, Ordering::AcqRel) != next {
        // A full queue already has a GUI wake. The consumer reads this current
        // value for every command, so a stale acknowledgement cannot overwrite it.
        let _ = control.send(Command::TrayStatusChanged);
    }
}

impl Watcher {
    pub(super) async fn start(
        connection: &Connection,
        control: Control,
        item_name: &'static str,
    ) -> Self {
        let available = Arc::new(AtomicBool::new(false));
        let observer = Self::subscribe(connection, control, item_name, available.clone()).await;
        if let Err(error) = &observer {
            eprintln!("Tray watcher unavailable: {error}");
        }
        Self {
            available,
            _observer: observer.ok(),
        }
    }

    async fn subscribe(
        connection: &Connection,
        control: Control,
        item_name: &'static str,
        available: Arc<AtomicBool>,
    ) -> zbus::Result<Task<()>> {
        let bus = fdo::DBusProxy::new(connection).await?;
        let mut changes = bus
            .receive_name_owner_changed_with_args(&[(0, WATCHER)])
            .await?;
        // A reply interrupted by a handover is still pending, not a refusal.
        // Resolve the replacement before deciding hidden startup. Under
        // continuous churn, bound retries as well as each two-second RPC.
        let deadline = Instant::now() + Duration::from_secs(3);
        let mut first = register(connection, &bus, &mut changes, item_name).await?;
        while matches!(first, Registration::Changed) && Instant::now() < deadline {
            first = register(connection, &bus, &mut changes, item_name).await?;
        }
        if let Registration::Observed(value) = first {
            available.store(value, Ordering::Release);
        }
        let client = connection.clone();
        Ok(connection.executor().spawn(
            async move {
                let mut retry = matches!(first, Registration::Changed);
                let result: zbus::Result<()> = async {
                    loop {
                        if !retry {
                            owner_change(&mut changes).await?;
                        }
                        publish(&available, &control, false);
                        match register(&client, &bus, &mut changes, item_name).await? {
                            Registration::Changed => retry = true,
                            Registration::Observed(value) => {
                                publish(&available, &control, value);
                                retry = false;
                            }
                        }
                    }
                }
                .await;
                if let Err(error) = result {
                    publish(&available, &control, false);
                    eprintln!("Tray watcher observation ended: {error}");
                }
            },
            "Linux tray watcher",
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc::{TryRecvError, sync_channel};

    #[test]
    fn only_the_current_repliers_empty_acknowledgement_confirms_registration() {
        assert!(accepted(":1.2", Some(":1.2"), true, Some(":1.2")));
        assert!(!accepted(":1.2", Some(":1.2"), true, Some(":1.3")));
        assert!(!accepted(":1.2", Some(":1.3"), true, Some(":1.3")));
        assert!(!accepted(":1.2", Some(":1.2"), true, None));
        assert!(!accepted(":1.2", Some(":1.2"), false, Some(":1.2")));
    }

    #[test]
    fn a_full_input_queue_preserves_the_latest_watcher_outcome() {
        let (sender, commands) = sync_channel(1);
        let control = Control {
            sender,
            window: Default::default(),
            graphics_attention: Default::default(),
            appearance: Default::default(),
        };
        let available = AtomicBool::new(false);
        control.send(Command::Open).unwrap();
        publish(&available, &control, true);
        publish(&available, &control, false);
        assert!(matches!(commands.try_recv(), Ok(Command::Open)));
        assert!(!available.load(Ordering::Acquire));
        assert!(matches!(commands.try_recv(), Err(TryRecvError::Empty)));
        publish(&available, &control, true);
        assert!(matches!(
            commands.try_recv(),
            Ok(Command::TrayStatusChanged)
        ));
        assert!(available.load(Ordering::Acquire));
    }
}
