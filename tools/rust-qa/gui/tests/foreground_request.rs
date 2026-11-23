#[path = "../src/foreground_request.rs"]
mod foreground_request;

use desktop_lifecycle::HostCommand;
use foreground_request::ForegroundRequest;

#[test]
fn explicit_open_waits_for_the_first_visible_root_and_never_retries_a_denial() {
    let mut request = ForegroundRequest::default();
    request.update(true, Some(HostCommand::ShowAndFocus));
    assert_eq!(request.take_visible(|| None::<usize>), None);
    request.update(false, None);
    assert_eq!(request.take_visible(|| Some(42)), Some(42));
    assert_eq!(
        request.take_visible(|| panic!("already attempted")),
        None::<usize>
    );
    request.update(true, Some(HostCommand::ShowAndFocus));
    assert_eq!(request.take_visible(|| Some(42)), Some(42));
}

#[test]
fn implicit_reveal_and_shutdown_cannot_request_foreground() {
    let mut request = ForegroundRequest::default();
    request.update(false, Some(HostCommand::ShowAndFocus));
    assert_eq!(
        request.take_visible(|| panic!("implicit reveal")),
        None::<usize>
    );
    for action in [HostCommand::Hide, HostCommand::StopBackground] {
        request.update(true, Some(HostCommand::ShowAndFocus));
        request.update(false, Some(action));
        assert_eq!(
            request.take_visible(|| panic!("request cancelled")),
            None::<usize>
        );
    }
    request.update(true, None);
    assert_eq!(
        request.take_visible(|| panic!("already draining")),
        None::<usize>
    );
}
