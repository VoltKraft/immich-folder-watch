//! Wait for the Shell to recognize a freshly installed, verified notification shortcut.

use std::time::Duration;

const NOT_FOUND: i32 = 0x8007_0490_u32 as i32;
const INTERVAL: Duration = Duration::from_millis(500);
const BUDGET: Duration = Duration::from_secs(8);
const MAX_ATTEMPTS: u32 = 17;

pub(super) fn wait<T, S>(
    mut query: impl FnMut(u32) -> Result<(T, Result<S, i32>), i32>,
    mut elapsed: impl FnMut() -> Duration,
    mut sleep: impl FnMut(Duration),
) -> Result<(T, Option<S>), i32> {
    let mut number = 1;
    loop {
        let last = match query(number) {
            Ok((notifier, Ok(setting))) => return Ok((notifier, Some(setting))),
            // Retain this exact notifier if only its optional Setting query was unavailable.
            Ok((notifier, Err(NOT_FOUND))) => Ok((notifier, None)),
            Err(NOT_FOUND) => Err(NOT_FOUND),
            Ok((_, Err(other))) | Err(other) => return Err(other),
        };
        if number == MAX_ATTEMPTS || elapsed() + INTERVAL >= BUDGET {
            return last;
        }
        sleep(INTERVAL);
        if elapsed() >= BUDGET {
            return last;
        }
        number += 1;
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
                match n {
                    1 => Err(NOT_FOUND),
                    2 => Ok((n, Err(NOT_FOUND))),
                    _ => Ok((n, Ok(3))),
                }
            },
            || clock.get(),
            |delay| clock.set(clock.get() + delay),
        );
        assert_eq!(setting, Ok((3, Some(3))));
        assert_eq!(calls, [1, 2, 3]);
        assert_eq!(clock.get(), INTERVAL * 2);
        let denied = 0x8007_0005_u32 as i32;
        for refusal in [Err(denied), Ok((1, Err(denied)))] {
            assert_eq!(
                wait::<_, ()>(
                    |_| refusal,
                    || Duration::ZERO,
                    |_| panic!("unexpected retry")
                ),
                Err(denied)
            );
        }
    }

    #[test]
    fn attempt_limit_and_elapsed_deadline_each_stop_the_queries() {
        let mut last = 0;
        assert_eq!(
            wait::<_, ()>(
                |n| {
                    last = n;
                    Ok((n, Err(NOT_FOUND)))
                },
                || Duration::ZERO,
                |_| {}
            ),
            Ok((MAX_ATTEMPTS, None))
        );
        assert_eq!(last, MAX_ATTEMPTS);
        let clock = Cell::new(Duration::ZERO);
        assert_eq!(
            wait::<_, ()>(
                |n| {
                    assert_eq!(n, 1);
                    Ok((n, Err(NOT_FOUND)))
                },
                || clock.get(),
                |_| clock.set(BUDGET)
            ),
            Ok((1, None))
        );
    }

    #[test]
    fn the_last_failed_creation_cannot_reuse_an_earlier_notifier() {
        let clock = Cell::new(Duration::ZERO);
        assert_eq!(
            wait::<_, ()>(
                |n| if n == 1 {
                    Ok((n, Err(NOT_FOUND)))
                } else {
                    Err(NOT_FOUND)
                },
                || clock.get(),
                |delay| clock.set(clock.get() + delay)
            ),
            Err(NOT_FOUND)
        );
    }
}
