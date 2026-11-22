//! Linux desktop appearance from the read-only XDG Settings portal.
use futures_lite::{StreamExt, future};
use std::collections::HashMap;
use std::io;
use std::thread;
use std::time::Duration;
use zbus::{Connection, Proxy, connection::Builder, zvariant::OwnedValue};

const NAMESPACE: &str = "org.freedesktop.appearance";
type Settings = HashMap<String, HashMap<String, OwnedValue>>;

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub(super) enum Scheme {
    #[default]
    System,
    Dark,
    Light,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub(super) struct Appearance {
    pub scheme: Scheme,
    pub high_contrast: bool,
}

impl Appearance {
    fn read(settings: &Settings) -> Self {
        let value = |name| u32::try_from(settings.get(NAMESPACE)?.get(name)?).ok();
        Self {
            scheme: match value("color-scheme") {
                Some(1) => Scheme::Dark,
                Some(2) => Scheme::Light,
                _ => Scheme::System,
            },
            high_contrast: value("contrast") == Some(1),
        }
    }
}

async fn observe(connection: &Connection, update: impl Fn(Appearance)) -> zbus::Result<()> {
    let proxy = Proxy::new(
        connection,
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Settings",
    )
    .await?;
    // Subscribe before the first read. Re-read a coherent snapshot after a change or service restart.
    let mut changes = proxy
        .receive_signal_with_args("SettingChanged", &[(0, NAMESPACE)])
        .await?;
    let mut owners = proxy.receive_owner_changed().await?;
    loop {
        let state: zbus::Result<Settings> = proxy.call("ReadAll", &(vec![NAMESPACE],)).await;
        update(state.as_ref().map(Appearance::read).unwrap_or_default());
        // Yield to incoming events. Closing the monitor connection terminates both paths.
        let next = future::or(async { changes.next().await.is_some() }, async {
            owners.next().await.is_some()
        })
        .await;
        if !next {
            return Ok(());
        }
    }
}

pub(super) struct Monitor {
    connection: Option<Connection>,
    worker: Option<thread::JoinHandle<()>>,
}

impl Monitor {
    pub(super) fn start(
        update: impl Fn(Appearance) + Send + 'static,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let connection = future::block_on(
            Builder::session()?
                .method_timeout(Duration::from_secs(2))
                .build(),
        )?;
        let client = connection.clone();
        let worker = thread::Builder::new()
            .name("desktop-appearance".into())
            .spawn(move || {
                if let Err(error) = future::block_on(future::or(observe(&client, update), async {
                    client.closed().await;
                    Ok(())
                })) {
                    eprintln!("Desktop appearance observation ended: {error}");
                }
            })?;
        Ok(Self {
            connection: Some(connection),
            worker: Some(worker),
        })
    }

    pub(super) fn stop(&mut self) -> io::Result<()> {
        let closed = self
            .connection
            .take()
            .map(|bus| future::block_on(bus.close()))
            .transpose();
        if let Some(worker) = self.worker.take() {
            worker
                .join()
                .map_err(|_| io::Error::other("Appearance worker panicked"))?;
        }
        closed.map(|_| ()).map_err(io::Error::other)
    }
}

impl Drop for Monitor {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_known_typed_portal_values_select_appearance() {
        assert_eq!(Appearance::read(&Settings::new()), Appearance::default());
        let mut fields = HashMap::from([
            ("color-scheme".to_owned(), OwnedValue::from(2u32)),
            ("contrast".to_owned(), OwnedValue::from(1u32)),
        ]);
        let known = Settings::from([(NAMESPACE.to_owned(), fields.clone())]);
        assert_eq!(
            Appearance::read(&known),
            Appearance {
                scheme: Scheme::Light,
                high_contrast: true
            }
        );
        fields.insert("color-scheme".into(), OwnedValue::from(3u32));
        fields.insert("contrast".into(), OwnedValue::from(true));
        assert_eq!(
            Appearance::read(&Settings::from([(NAMESPACE.to_owned(), fields)])),
            Appearance::default()
        );
    }
}
