//! Export the shipping Linux tray menu on the elected application's connection.
use super::{Actions, Command};
use std::collections::HashMap;
use std::sync::{Arc, Mutex, Weak};
use zbus::object_server::SignalEmitter;
use zbus::zvariant::{ObjectPath, OwnedValue, Value};
use zbus::{Connection, DBusError, Task, fdo, interface};

pub(super) const PATH: &str = "/StatusNotifierItem/Menu";
const IDS: [i32; 3] = [1, 2, 3];
type Properties = HashMap<&'static str, Value<'static>>;
type Layout = (i32, Properties, Vec<Value<'static>>);

#[derive(Debug, DBusError)]
#[zbus(prefix = "com.canonical.dbusmenu.Error")]
enum PropertyError {
    InvalidProperty(String),
    #[zbus(error)]
    ZBus(zbus::Error),
}

pub(super) struct Labels {
    german: bool,
    revision: u32,
    publishing: bool,
}

impl Default for Labels {
    fn default() -> Self {
        Self {
            german: true,
            revision: 1,
            publishing: false,
        }
    }
}

pub(super) type SharedLabels = Arc<Mutex<Labels>>;

impl Labels {
    fn change(&mut self, german: bool) -> Option<u32> {
        if german == self.german {
            return None;
        }
        self.german = german;
        self.revision = self.revision.wrapping_add(1);
        if self.publishing {
            return None;
        }
        self.publishing = true;
        Some(self.revision)
    }

    fn next_revision(&mut self, sent: u32) -> Option<u32> {
        if self.revision != sent {
            return Some(self.revision);
        }
        self.publishing = false;
        None
    }
}

// The primary owns the signal writer. A stale UI language control cannot
// keep the connection alive after the primary starts graceful shutdown.
pub(super) struct Publisher {
    connection: Connection,
    labels: SharedLabels,
    writer: Mutex<Option<Task<()>>>,
}

impl Publisher {
    pub(super) fn new(connection: Connection, labels: SharedLabels) -> Arc<Self> {
        Arc::new(Self {
            connection,
            labels,
            writer: Mutex::default(),
        })
    }

    pub(super) fn language(self: &Arc<Self>) -> TrayLanguage {
        TrayLanguage(Arc::downgrade(self))
    }
}

#[derive(Clone)]
pub(crate) struct TrayLanguage(Weak<Publisher>);

impl TrayLanguage {
    pub(crate) fn set_german(&self, german: bool) {
        let Some(publisher) = self.0.upgrade() else {
            return;
        };
        let mut writer = publisher
            .writer
            .lock()
            .expect("tray publisher mutex poisoned");
        let revision = publisher
            .labels
            .lock()
            .expect("tray language mutex poisoned")
            .change(german);
        let Some(mut revision) = revision else { return };
        let labels = publisher.labels.clone();
        let emitter = SignalEmitter::from_parts(
            publisher.connection.clone(),
            ObjectPath::from_static_str_unchecked(PATH),
        );
        // A newer language is visible to GetLayout immediately. Only one
        // task publishes signals even when another change arrives during send.
        *writer = Some(publisher.connection.executor().spawn(
            async move {
                loop {
                    if let Err(error) = Menu::layout_updated(&emitter, revision, 0).await {
                        eprintln!("Tray menu layout update failed: {error}");
                    }
                    let next = labels
                        .lock()
                        .expect("tray language mutex poisoned")
                        .next_revision(revision);
                    let Some(next) = next else { break };
                    revision = next;
                }
            },
            "Linux tray menu layout update",
        ));
    }
}

pub(super) struct Menu {
    actions: Actions,
    labels: SharedLabels,
}

impl Menu {
    pub(super) fn new(actions: Actions, labels: SharedLabels) -> Self {
        Self { actions, labels }
    }

    fn snapshot(&self) -> (u32, bool) {
        let labels = self.labels.lock().expect("tray language mutex poisoned");
        (labels.revision, labels.german)
    }

    fn properties(id: i32, names: &[&str], german: bool) -> Properties {
        let props = match id {
            0 => Properties::from([("children-display", "submenu".into())]),
            1..=3 => {
                let labels = if german {
                    ["GUI öffnen", "Neustart", "Beenden"]
                } else {
                    ["Open GUI", "Restart", "Quit"]
                };
                Properties::from([
                    ("label", labels[(id - 1) as usize].into()),
                    ("enabled", true.into()),
                    ("visible", true.into()),
                ])
            }
            _ => Properties::new(),
        };
        if names.is_empty() {
            return props;
        }
        props
            .into_iter()
            .filter(|(name, _)| names.contains(name))
            .collect()
    }

    fn activate(&self, id: i32, event: &str) -> fdo::Result<()> {
        if event != "clicked" {
            return Ok(());
        }
        let command = match id {
            1 => Command::Open,
            2 => Command::RestartWorker,
            3 => Command::Quit,
            _ => return Ok(()),
        };
        self.actions.send(command)
    }
}

#[interface(name = "com.canonical.dbusmenu")]
impl Menu {
    #[zbus(out_args("revision", "layout"))]
    fn get_layout(
        &self,
        parent_id: i32,
        recursion_depth: i32,
        property_names: Vec<&str>,
    ) -> (u32, Layout) {
        let (revision, german) = self.snapshot();
        let props = Self::properties(parent_id, &property_names, german);
        let mut children = Vec::new();
        if parent_id == 0 && recursion_depth != 0 {
            for id in IDS {
                let child: Layout = (
                    id,
                    Self::properties(id, &property_names, german),
                    Vec::new(),
                );
                children.push(child.into());
            }
        }
        (revision, (parent_id, props, children))
    }

    fn get_group_properties(
        &self,
        mut ids: Vec<i32>,
        property_names: Vec<&str>,
    ) -> Vec<(i32, Properties)> {
        let (_, german) = self.snapshot();
        if ids.is_empty() {
            ids.extend(0..=3);
        }
        ids.into_iter()
            .map(|id| (id, Self::properties(id, &property_names, german)))
            .collect()
    }

    fn get_property(&self, id: i32, name: &str) -> Result<Value<'static>, PropertyError> {
        Self::properties(id, &[name], self.snapshot().1)
            .remove(name)
            .ok_or_else(|| PropertyError::InvalidProperty("Unknown menu item property".into()))
    }

    fn event(
        &self,
        id: i32,
        event_id: &str,
        _data: OwnedValue,
        _timestamp: u32,
    ) -> fdo::Result<()> {
        self.activate(id, event_id)
    }
    fn event_group(&self, events: Vec<(i32, &str, OwnedValue, u32)>) -> Vec<i32> {
        events
            .into_iter()
            .filter_map(|(id, event, _, _)| self.activate(id, event).err().map(|_| id))
            .collect()
    }

    fn about_to_show(&self, _id: i32) -> bool {
        false
    }
    #[zbus(out_args("updates_needed", "id_errors"))]
    fn about_to_show_group(&self, _ids: Vec<i32>) -> (Vec<i32>, Vec<i32>) {
        (Vec::new(), Vec::new())
    }

    #[zbus(property)]
    fn version(&self) -> u32 {
        3
    }
    #[zbus(property)]
    fn text_direction(&self) -> &'static str {
        "ltr"
    }
    #[zbus(property)]
    fn status(&self) -> &'static str {
        "normal"
    }
    #[zbus(property)]
    fn icon_theme_path(&self) -> Vec<&'static str> {
        Vec::new()
    }

    #[zbus(signal)]
    async fn layout_updated(
        emitter: &SignalEmitter<'_>,
        revision: u32,
        parent: i32,
    ) -> zbus::Result<()>;
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Control;
    use std::sync::mpsc::sync_channel;
    use zbus::zvariant::Type;

    fn menu_with_queue(capacity: usize) -> (Menu, std::sync::mpsc::Receiver<Command>) {
        let (sender, commands) = sync_channel(capacity);
        let actions = Actions {
            control: Control {
                sender,
                window: Default::default(),
                graphics_attention: Default::default(),
                appearance: Default::default(),
            },
            quitting: Arc::default(),
        };
        (Menu::new(actions, SharedLabels::default()), commands)
    }

    #[test]
    fn grouped_clicks_report_full_queues_and_share_shutdown_with_other_interfaces() {
        let (menu, commands) = menu_with_queue(1);
        let event = |id, name| (id, name, OwnedValue::from(0), 0);
        let errors = menu.event_group(vec![
            event(1, "hovered"),
            event(2, "clicked"),
            event(3, "clicked"),
        ]);
        assert_eq!(errors, vec![3]);
        assert!(matches!(commands.try_recv(), Ok(Command::RestartWorker)));
        menu.event(3, "clicked", OwnedValue::from(0), 0).unwrap();
        assert!(matches!(commands.try_recv(), Ok(Command::Quit)));
        assert!(matches!(
            menu.actions.send(Command::Open),
            Err(fdo::Error::Failed(_))
        ));
    }

    #[test]
    fn the_panel_gets_the_shipping_rows_and_selected_properties() {
        let (menu, _commands) = menu_with_queue(1);
        let (revision, (id, root, children)) = menu.get_layout(0, -1, vec![]);
        assert_eq!((revision, id), (1, 0));
        assert_eq!(root["children-display"], Value::from("submenu"));
        assert_eq!(Layout::SIGNATURE.to_string(), "(ia{sv}av)");
        let rows: Vec<_> = children
            .iter()
            .map(|value| {
                let Value::Structure(row) = value else {
                    panic!("expected a menu row")
                };
                assert_eq!(row.signature(), Layout::SIGNATURE);
                let fields = row.fields();
                let props: HashMap<String, OwnedValue> =
                    fields[1].try_clone().unwrap().try_into().unwrap();
                (
                    i32::try_from(&fields[0]).unwrap(),
                    String::try_from(props["label"].try_clone().unwrap()).unwrap(),
                )
            })
            .collect();
        assert_eq!(
            rows,
            vec![
                (1, "GUI öffnen".into()),
                (2, "Neustart".into()),
                (3, "Beenden".into())
            ]
        );
        assert!(menu.get_layout(0, 0, vec![]).1.2.is_empty());
        menu.labels.lock().unwrap().change(false);
        let (revision, (_, props, descendants)) = menu.get_layout(2, -1, vec!["label"]);
        assert_eq!(revision, 2);
        assert_eq!(props, Properties::from([("label", Value::from("Restart"))]));
        assert!(descendants.is_empty());
        assert!(menu.get_property(3, "missing").is_err());
    }

    #[test]
    fn language_changes_share_one_writer_until_the_latest_revision_is_sent() {
        let mut labels = Labels::default();
        assert_eq!(labels.change(true), None);
        assert_eq!(labels.change(false), Some(2));
        assert_eq!(labels.change(true), None);
        assert_eq!(labels.next_revision(2), Some(3));
        assert_eq!(labels.next_revision(3), None);
        assert_eq!(labels.change(false), Some(4));
    }
}
