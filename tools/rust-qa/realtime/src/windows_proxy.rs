//! Manual proxy settings from the active Windows connection.

use reqwest::Url;
use std::net::IpAddr;

use crate::{Error, transport::SelectedProxy};

#[cfg(windows)]
pub(crate) fn current_user(api: &Url) -> Result<SelectedProxy, Error> {
    let settings = ifw_windows_proxy_settings::current_user().map_err(|_| Error::SystemProxy)?;
    if settings.automatic {
        return Err(Error::AutomaticProxy);
    }
    manual(
        api,
        settings.proxies.as_deref(),
        settings.bypass.as_deref(),
        |ip| ifw_windows_proxy_settings::has_local_address(ip).map_err(|_| Error::SystemProxy),
    )
}

// Windows manual bypass patterns match the whole IDN host with ASCII-insensitive
// literal characters and '*' wildcards. The URL parser already encoded IDNs.
fn matches_pattern(host: &str, pattern: &str) -> bool {
    let pattern = pattern.to_ascii_lowercase();
    let host = host.to_ascii_lowercase();
    let mut parts = pattern.split('*');
    let first = parts.next().unwrap_or_default();
    let Some(mut tail) = host.strip_prefix(first) else {
        return false;
    };
    let Some(last) = parts.next_back() else {
        return tail.is_empty();
    };
    if let Some(rest) = tail.strip_suffix(last) {
        tail = rest;
    } else {
        return false;
    }
    for part in parts {
        let Some((_, after)) = tail.split_once(part) else {
            return false;
        };
        tail = after;
    }
    true
}

fn bypassed(
    api: &Url,
    list: &str,
    is_local: impl Fn(IpAddr) -> Result<bool, Error>,
) -> Result<bool, Error> {
    let host = api
        .host_str()
        .ok_or(Error::Origin)?
        .trim_matches(['[', ']']);
    let mut local = false;
    for field in list.split(';') {
        let mut field = field.trim_start_matches(' ');
        for prefix in ["http://", "https://"] {
            if field
                .get(..prefix.len())
                .is_some_and(|s| s.eq_ignore_ascii_case(prefix))
            {
                field = &field[prefix.len()..];
                break;
            }
        }
        let entry = field
            .trim_start_matches('[')
            .split([' ', ']'])
            .next()
            .unwrap_or_default();
        if entry.eq_ignore_ascii_case("<local>") {
            local = true;
        } else if !entry.is_empty() && matches_pattern(host, entry) {
            return Ok(true);
        }
    }
    if !local {
        return Ok(false);
    }
    match host.parse::<IpAddr>() {
        Ok(addr) if addr.is_loopback() => Ok(true),
        Ok(addr) => is_local(addr),
        Err(_) => Ok(!host.contains('.') || host.eq_ignore_ascii_case("localhost")),
    }
}

pub(crate) fn manual(
    api: &Url,
    proxies: Option<&str>,
    bypass: Option<&str>,
    is_local: impl Fn(IpAddr) -> Result<bool, Error>,
) -> Result<SelectedProxy, Error> {
    let mut endpoint = None;
    let secure = matches!(api.scheme(), "https" | "wss");
    for token in proxies
        .unwrap_or_default()
        .split([';', ' ', '\t', '\r', '\n'])
        .filter(|s| !s.is_empty())
    {
        let authority = if let Some(value) = token.strip_prefix("http=") {
            if secure {
                continue;
            }
            value
        } else if let Some(value) = token.strip_prefix("https=") {
            if !secure {
                continue;
            }
            value
        } else {
            token
        };
        // System.Net treats both URL prefixes in the manual Windows syntax as
        // a named HTTP proxy. The protocol selector before '=' is independent.
        let authority = authority
            .strip_prefix("http://")
            .or_else(|| authority.strip_prefix("https://"))
            .unwrap_or(authority);
        if authority.is_empty()
            || authority.contains(['=', '/', '@', '?', '#', '\\'])
            || endpoint.is_some()
        {
            return Err(Error::SystemProxy);
        }
        let url = Url::parse(&format!("http://{authority}")).map_err(|_| Error::SystemProxy)?;
        if url.host().is_none() || url.port_or_known_default() == Some(0) {
            return Err(Error::SystemProxy);
        }
        endpoint = Some(url);
    }
    let bypass = endpoint.is_some() && bypassed(api, bypass.unwrap_or_default(), is_local)?;
    Ok(SelectedProxy { endpoint, bypass })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn manual_system_proxy_uses_the_selected_group_and_windows_bypass_rules() {
        let http = "http=first.test:81;https=second.test:82";
        for (scheme, port) in [("http", 81), ("ws", 81), ("https", 82), ("wss", 82)] {
            let api = Url::parse(&format!("{scheme}://photos.example.test/api")).unwrap();
            for (list, direct) in [
                ("", false),
                ("*.example.test", true),
                ("photos.*.test", true),
                ("photo*photos.example.test", false),
                ("http://PHOTOS.EXAMPLE.TEST", true),
                ("<local>", false),
                ("photos.example.test:82", false),
            ] {
                let result = manual(&api, Some(http), Some(list), |_| panic!())
                    .unwrap()
                    .route();
                assert_eq!(
                    result.as_ref().map(Url::port_or_known_default),
                    if direct { None } else { Some(Some(port)) }
                );
            }
        }
        let api = Url::parse("https://127.0.0.1:443/api").unwrap();
        for proxy in [None, Some("http=other.test:81")] {
            assert!(
                manual(&api, proxy, None, |_| panic!())
                    .unwrap()
                    .route()
                    .is_none()
            );
        }
        assert!(
            manual(&api, Some("proxy.test"), Some("<local>"), |_| panic!())
                .unwrap()
                .route()
                .is_none()
        );
        assert!(manual(&api, Some("a.test;b.test"), None, |_| panic!()).is_err());
    }

    #[test]
    fn local_bypass_asks_for_actual_nonloopback_ip_addresses() {
        let api = Url::parse("https://192.0.2.15/api").unwrap();
        for local in [true, false] {
            let r = manual(&api, Some("proxy.test"), Some("<local>"), |addr| {
                assert_eq!(addr, "192.0.2.15".parse::<IpAddr>().unwrap());
                Ok(local)
            })
            .unwrap();
            assert_eq!(r.route().is_none(), local);
        }
    }
}
