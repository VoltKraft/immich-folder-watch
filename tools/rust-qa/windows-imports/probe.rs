//! Exercise the same system ABI, Win32 binding and feature identifier as ring.

#![no_std]

use windows_sys::Win32::System::Threading::{
    IsProcessorFeaturePresent, PF_ARM_V8_CRYPTO_INSTRUCTIONS_AVAILABLE,
};

#[unsafe(no_mangle)]
pub extern "system" fn ifw_feature(feature: u32) -> i32 {
    // Windows documents this query for every feature ID. It has no pointer arguments.
    unsafe { IsProcessorFeaturePresent(feature) }
}

#[unsafe(no_mangle)]
pub extern "system" fn ifw_ring_feature() -> i32 {
    ifw_feature(PF_ARM_V8_CRYPTO_INSTRUCTIONS_AVAILABLE)
}
