//! Bounded access to shipping-format configuration for the native assessments.
#![forbid(unsafe_code)]

mod anchors;
#[doc(hidden)]
pub mod codec;
#[doc(hidden)]
pub mod encoding;
#[doc(hidden)]
pub mod model;
mod scalar_breaks;
#[cfg(target_os = "linux")]
pub mod startup_language;
