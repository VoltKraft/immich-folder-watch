//! Inbox WinRT toast delivery to the notification history of a test-owned shortcut.

use std::ffi::OsStr;
use std::fs;
use std::io::Write;
use std::path::Path;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use windows::Data::Xml::Dom::XmlDocument;
use windows::Foundation::{DateTime, IReference, PropertyValue};
use windows::UI::Notifications::{
    NotificationMirroring, NotificationSetting, ToastNotification, ToastNotificationManager,
};
use windows::Win32::Foundation::HANDLE;
use windows::Win32::Security::{GetTokenInformation, TOKEN_ELEVATION, TOKEN_QUERY, TokenElevation};
use windows::Win32::Storage::EnhancedStorage::{
    PKEY_AppUserModel_ID, PKEY_AppUserModel_ToastActivatorCLSID,
};
use windows::Win32::System::Com::StructuredStorage::{
    InitPropVariantFromCLSID, PROPVARIANT, PVCHF_DEFAULT, PropVariantChangeType, PropVariantToGUID,
};
use windows::Win32::System::Com::{
    CLSCTX_INPROC_SERVER, CoCreateInstance, IPersistFile, STGM_READ,
};
use windows::Win32::System::RemoteDesktop::ProcessIdToSessionId;
use windows::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};
use windows::Win32::System::Variant::VT_LPWSTR;
use windows::Win32::System::WinRT::{RO_INIT_SINGLETHREADED, RoInitialize, RoUninitialize};
use windows::Win32::UI::Shell::PropertiesSystem::IPropertyStore;
use windows::Win32::UI::Shell::{
    FOLDERID_Programs, IShellLinkW, SHCNE_CREATE, SHCNF_FLUSHNOWAIT, SHCNF_PATHW, SHChangeNotify,
    SLGP_RAWPATH, SetCurrentProcessExplicitAppUserModelID, ShellLink,
};
use windows::core::{BSTR, Error, GUID, HRESULT, HSTRING, Interface, Owned, PCWSTR, Result, w};

use crate::shortcuts::{known_folder, read_string};
use crate::toast_readiness;
use crate::{invalid, wide};

const LINK: &str = "IFW synthetic notification.lnk";

struct Apartment;
impl Drop for Apartment {
    fn drop(&mut self) {
        // Paired with this thread's successful RoInitialize after all interfaces drop.
        unsafe { RoUninitialize() };
    }
}

struct Identity<'a> {
    token: &'a str,
    aumid: HSTRING,
    group: HSTRING,
    stub: GUID,
}

impl<'a> Identity<'a> {
    fn new(token: &'a str) -> Result<Self> {
        if token.len() != 32
            || !token
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
            || token.as_bytes()[12] != b'4'
            || !b"89ab".contains(&token.as_bytes()[16])
        {
            return Err(invalid());
        }
        Ok(Self {
            token,
            aumid: format!("IFW.RustQA.Toast.{token}").into(),
            group: format!("g{}", &token[16..31]).into(),
            stub: GUID::from_u128(u128::from_str_radix(token, 16).map_err(|_| invalid())?),
        })
    }
    fn tag(&self, quiet: bool) -> HSTRING {
        format!("{}{}", if quiet { 'q' } else { 'n' }, &self.token[..15]).into()
    }
    fn title(&self, mode: &str) -> String {
        format!("IFW synthetic {mode} {}", self.token)
    }
    fn body(&self, mode: &str) -> String {
        format!("Rust {mode} notification history {}", self.token)
    }
}

fn process_identity(require_standard_user: bool) -> Result<()> {
    let pid = std::process::id();
    let mut session = 0;
    let mut elevation = TOKEN_ELEVATION::default();
    let mut returned = 0;
    let mut token = HANDLE::default();
    // Query only our own process. No token duplication or identity changes.
    unsafe {
        ProcessIdToSessionId(pid, &mut session)?;
        OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token)?;
        let token = Owned::new(token);
        GetTokenInformation(
            *token,
            TokenElevation,
            Some(std::ptr::from_mut(&mut elevation).cast()),
            size_of::<TOKEN_ELEVATION>() as u32,
            &mut returned,
        )?;
    }
    if returned != size_of::<TOKEN_ELEVATION>() as u32
        || (require_standard_user && elevation.TokenIsElevated != 0)
    {
        return Err(invalid());
    }
    println!(
        "pid={pid}\nsession={session}\nelevated={}",
        elevation.TokenIsElevated != 0
    );
    Ok(())
}

fn prepare_link(path: &Path, id: &Identity<'_>) -> Result<()> {
    // The supervisor owns the enclosing fixture. Only the completed bytes will be installed.
    drop(
        fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)?,
    );
    let target = wide(std::env::current_exe()?.as_os_str());
    let name = wide(path.as_os_str());
    unsafe {
        let link: IShellLinkW = CoCreateInstance(&ShellLink, None, CLSCTX_INPROC_SERVER)?;
        link.SetPath(PCWSTR(target.as_ptr()))?;
        link.SetArguments(w!("--toast-shortcut"))?;
        link.SetDescription(w!("IFW synthetic notification history"))?;
        let props: IPropertyStore = link.cast()?;
        let mut app = PROPVARIANT::default();
        PropVariantChangeType(
            &mut app,
            &PROPVARIANT::from(id.aumid.to_string_lossy().as_str()),
            PVCHF_DEFAULT,
            VT_LPWSTR,
        )?;
        props.SetValue(&PKEY_AppUserModel_ID, &app)?;
        props.SetValue(
            &PKEY_AppUserModel_ToastActivatorCLSID,
            &InitPropVariantFromCLSID(&id.stub)?,
        )?;
        props.Commit()?;
        link.cast::<IPersistFile>()?
            .Save(PCWSTR(name.as_ptr()), true)?;
    }
    println!("prepared=true");
    Ok(())
}

fn verify_link(path: &Path, id: &Identity<'_>) -> Result<()> {
    let name = wide(path.as_os_str());
    unsafe {
        let link: IShellLinkW = CoCreateInstance(&ShellLink, None, CLSCTX_INPROC_SERVER)?;
        link.cast::<IPersistFile>()?
            .Load(PCWSTR(name.as_ptr()), STGM_READ)?;
        let props: IPropertyStore = link.cast()?;
        let app = props.GetValue(&PKEY_AppUserModel_ID)?;
        let guid = PropVariantToGUID(&props.GetValue(&PKEY_AppUserModel_ToastActivatorCLSID)?)?;
        let mut buffer = vec![0u16; 32768];
        link.GetPath(&mut buffer, std::ptr::null_mut(), SLGP_RAWPATH.0 as u32)?;
        let target = fs::canonicalize(read_string(&buffer))?;
        link.GetArguments(&mut buffer)?;
        if target != fs::canonicalize(std::env::current_exe()?)?
            || read_string(&buffer) != "--toast-shortcut"
            || app.vt() != VT_LPWSTR
            || BSTR::try_from(&app)?[..] != id.aumid[..]
            || guid != id.stub
        {
            return Err(invalid());
        }
    }
    println!("installedLinkVerified=true");
    Ok(())
}

fn post(id: &Identity<'_>, quiet: bool) -> Result<()> {
    let mode = if quiet { "quiet" } else { "normal" };
    let started = Instant::now();
    let (notifier, setting) = toast_readiness::wait(
        |attempt| {
            println!("phase=notifier-create");
            let created = ToastNotificationManager::CreateToastNotifierWithId(&id.aumid);
            println!(
                "ready.{attempt}.create={}",
                created.as_ref().err().map_or(0, |e| e.code().0)
            );
            let notifier = created.map_err(|e| e.code().0)?;
            println!("phase=notifier-setting");
            let setting = notifier.Setting();
            println!(
                "ready.{attempt}.setting={}",
                setting.as_ref().err().map_or(0, |e| e.code().0)
            );
            Ok((notifier, setting.map_err(|e| e.code().0)))
        },
        || started.elapsed(),
        std::thread::sleep,
    )
    .map_err(|hr| Error::from_hresult(HRESULT(hr)))?;
    if let Some(setting) = setting {
        println!("setting={}", setting.0);
        if setting != NotificationSetting::Enabled {
            return Ok(());
        }
    } else {
        println!("readinessElapsedMs={}", started.elapsed().as_millis());
        println!("setting=unavailable");
    }
    let (title, body) = (id.title(mode), id.body(mode));
    // This synthetic protocol has no registered handler and is never invoked.
    // The unregistered shortcut CLSID enables history on unpackaged desktop apps.
    let xml = format!(
        r#"<toast activationType="protocol" launch="ifw-rw02-{}:history"><visual><binding template="ToastGeneric"><text>{title}</text><text>{body}</text></binding></visual><audio silent="true"/></toast>"#,
        id.token
    );
    println!("phase=content");
    let content = XmlDocument::new()?;
    content.LoadXml(&xml.into())?;
    let toast = ToastNotification::CreateToastNotification(&content)?;
    toast.SetTag(&id.tag(quiet))?;
    toast.SetGroup(&id.group)?;
    toast.SetSuppressPopup(quiet)?;
    toast.SetNotificationMirroring(NotificationMirroring::Disabled)?;
    // WinRT uses 100 ns intervals from 1601. Expire even if a disposable job is interrupted.
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| invalid())?;
    let ticks = i64::try_from(now.as_nanos() / 100).map_err(|_| invalid())?;
    let expiration = DateTime {
        UniversalTime: ticks
            .checked_add(116_444_736_000_000_000 + 3_000_000_000)
            .ok_or_else(invalid)?,
    };
    let boxed: IReference<DateTime> = PropertyValue::CreateDateTime(expiration)?.cast()?;
    toast.SetExpirationTime(&boxed)?;
    if toast.Tag()? != id.tag(quiet)
        || toast.Group()? != id.group
        || toast.SuppressPopup()? != quiet
        || toast.NotificationMirroring()? != NotificationMirroring::Disabled
        || toast.ExpirationTime()?.Value()? != expiration
    {
        return Err(invalid());
    }
    println!(
        "suppressPopup={quiet}\nmirroringDisabled=true\nexpirationTicks={}\nphase=show",
        expiration.UniversalTime
    );
    std::io::stdout().flush()?;
    let frequency = crate::tray::qpc_frequency()?;
    let begin = crate::tray::qpc()?;
    // The typed projection discards successful HRESULT values. Call the same generated
    // Show slot with both live interfaces on their originating apartment.
    let shown = unsafe { (notifier.vtable().Show)(notifier.as_raw(), toast.as_raw()) };
    let end = crate::tray::qpc()?;
    println!("showHresult={}", shown.0);
    println!("showFrequency={frequency}\nshowBeginQpc={begin}\nshowEndQpc={end}");
    shown.ok()?;
    println!("showReturned=true");
    Ok(())
}

fn inspect(id: &Identity<'_>) -> Result<()> {
    println!("phase=history");
    let rows = ToastNotificationManager::History()?.GetHistoryWithId(&id.aumid)?;
    let count = rows.Size()?;
    println!("count={count}");
    if count > 2 {
        return Err(invalid());
    }
    for index in 0..count {
        let row = rows.GetAt(index)?;
        let tag = row.Tag()?;
        let mode = if tag == id.tag(true) {
            "quiet"
        } else if tag == id.tag(false) {
            "normal"
        } else {
            return Err(invalid());
        };
        let group = row.Group()?;
        if group != id.group {
            return Err(invalid());
        }
        let fields = row.Content()?.GetElementsByTagName(&"text".into())?;
        if fields.Length()? != 2 {
            return Err(invalid());
        }
        let title = fields.Item(0)?.InnerText()?;
        let body = fields.Item(1)?.InnerText()?;
        if title.to_string_lossy() != id.title(mode) || body.to_string_lossy() != id.body(mode) {
            return Err(invalid());
        }
        println!(
            "{mode}.tag={tag}\n{mode}.group={group}\n{mode}.title={title}\n{mode}.body={body}"
        );
    }
    Ok(())
}

pub(super) fn run(area: &Path, token: &str, operation: &str, isolated_vm: bool) -> Result<()> {
    let arch = match std::env::consts::ARCH {
        "aarch64" => "ARM64",
        "x86_64" => "X64",
        _ => return Err(invalid()),
    };
    let temp = if isolated_vm {
        if arch != "X64" {
            return Err(invalid());
        }
        std::env::var_os("IFW_QA_VM_TEMP")
    } else {
        if std::env::var("RUNNER_ARCH").as_deref() != Ok(arch) {
            return Err(invalid());
        }
        std::env::var_os("RUNNER_TEMP")
    }
    .ok_or_else(invalid)?;
    if fs::canonicalize(area.parent().ok_or_else(invalid)?)? != fs::canonicalize(temp)? {
        return Err(invalid());
    }
    let id = Identity::new(token)?;
    println!("operation={operation}\naumid={}\nphase=identity", id.aumid);
    process_identity(isolated_vm)?;
    let app = wide(OsStr::new(&id.aumid.to_string_lossy()));
    unsafe {
        SetCurrentProcessExplicitAppUserModelID(PCWSTR(app.as_ptr()))?;
        RoInitialize(RO_INIT_SINGLETHREADED)?;
    }
    let _apartment = Apartment;
    let staged = area.join(LINK);
    if operation == "prepare" {
        return prepare_link(&staged, &id);
    }
    let installed = known_folder(&FOLDERID_Programs)?
        .join(format!("ifw-shell-{token}"))
        .join(LINK);
    println!("phase=shortcut");
    verify_link(&installed, &id)?;
    match operation {
        "register" => {
            let name = wide(installed.as_os_str());
            unsafe {
                SHChangeNotify(
                    SHCNE_CREATE,
                    SHCNF_PATHW | SHCNF_FLUSHNOWAIT,
                    Some(name.as_ptr().cast()),
                    None,
                )
            };
            println!("shellNotified=true");
            Ok(())
        }
        "inspect" => inspect(&id),
        "post-quiet" | "post-normal" => post(&id, operation == "post-quiet"),
        "remove-quiet" | "remove-normal" => {
            println!("phase=remove");
            ToastNotificationManager::History()?.RemoveGroupedTagWithId(
                &id.tag(operation == "remove-quiet"),
                &id.group,
                &id.aumid,
            )?;
            println!("removeReturned=true");
            Ok(())
        }
        _ => Err(invalid()),
    }
}
