//! Wait for the Shell to recognize a freshly installed, verified notification shortcut.

use std::time::Duration;

const NOT_FOUND: i32 = 0x8007_0490_u32 as i32;
const INTERVAL: Duration = Duration::from_millis(500);
const BUDGET: Duration = Duration::from_secs(8);
const MAX_ATTEMPTS: u32 = 17;

pub(super) fn wait<T>(
    mut query: impl FnMut(u32) -> Result<T, i32>,
    mut elapsed: impl FnMut() -> Duration,
    mut sleep: impl FnMut(Duration),
) -> Result<T, i32> {
    let mut number = 1;
    loop {
        match query(number) {
            Err(NOT_FOUND) if number < MAX_ATTEMPTS && elapsed() + INTERVAL < BUDGET => {
                sleep(INTERVAL);
                if elapsed() >= BUDGET {
                    return Err(NOT_FOUND);
                }
                number += 1;
            }
            result => return result,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;

    #[test]
    fn only_an_unrecognized_app_retries_and_the_first_setting_ends_the_wait() {
        let clock = Cell::new(Duration::ZERO);
        let mut calls = vec![];
        let setting = wait(
            |n| {
                calls.push(n);
                if n < 3 { Err(NOT_FOUND) } else { Ok(3) }
            },
            || clock.get(),
            |delay| clock.set(clock.get() + delay),
        );
        assert_eq!(setting, Ok(3));
        assert_eq!(calls, [1, 2, 3]);
        assert_eq!(clock.get(), INTERVAL * 2);
        let denied = 0x8007_0005_u32 as i32;
        assert_eq!(
            wait::<()>(
                |_| Err(denied),
                || Duration::ZERO,
                |_| panic!("unexpected retry")
            ),
            Err(denied)
        );
    }

    #[test]
    fn attempt_limit_and_elapsed_deadline_each_stop_the_queries() {
        let mut last = 0;
        assert_eq!(
            wait::<()>(
                |n| {
                    last = n;
                    Err(NOT_FOUND)
                },
                || Duration::ZERO,
                |_| {}
            ),
            Err(NOT_FOUND)
        );
        assert_eq!(last, MAX_ATTEMPTS);
        let clock = Cell::new(Duration::ZERO);
        assert_eq!(
            wait::<()>(
                |n| {
                    assert_eq!(n, 1);
                    Err(NOT_FOUND)
                },
                || clock.get(),
                |_| clock.set(BUDGET)
            ),
            Err(NOT_FOUND)
        );
    }
}
