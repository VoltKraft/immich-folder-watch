//! Own graphics generations and bounded renderer recovery independently of the desktop model.
use eframe::{egui_wgpu::WgpuSetup, wgpu};
use std::sync::Arc;
use std::sync::atomic::{AtomicU8, Ordering};
use std::time::Duration;

const ACTIVE: u8 = 0;
const LOST: u8 = 1;
const RELEASED: u8 = 2;

pub(super) fn allows_test_fault() -> bool {
    std::env::var("IFW_QA_ISOLATED").as_deref() == Ok("1")
        && matches!(
            std::env::var("IFW_QA_GRAPHICS").as_deref(),
            Ok("raw-loss" | "recover" | "repeated-loss" | "during-paint" | "unrelated-panic")
        )
}

#[derive(Clone, Copy)]
enum Failure {
    Initialization,
    DeviceLost,
}

pub(super) struct Graphics {
    device: Option<wgpu::Device>,
    state: Arc<AtomicU8>,
    #[cfg(target_os = "linux")]
    mesa_mailbox: Arc<std::sync::atomic::AtomicBool>,
    change_surface_mode: bool,
    attempt: u8,
    generation: u64,
    raw: bool,
    fault_on_paint: bool,
    queued_fault: bool,
    unrelated: bool,
    last_failure: Option<Failure>,
}

impl Graphics {
    pub(super) fn new() -> Self {
        let scenario = std::env::var("IFW_QA_GRAPHICS").unwrap_or_default();
        Self {
            device: None,
            state: Arc::new(AtomicU8::new(RELEASED)),
            #[cfg(target_os = "linux")]
            mesa_mailbox: Arc::default(),
            change_surface_mode: false,
            attempt: 0,
            generation: 0,
            raw: scenario == "raw-loss",
            fault_on_paint: matches!(scenario.as_str(), "during-paint" | "unrelated-panic"),
            queued_fault: false,
            unrelated: scenario == "unrelated-panic",
            last_failure: None,
        }
    }

    pub(super) fn configure(&mut self, options: &mut eframe::NativeOptions) {
        self.generation += 1;
        self.attempt += 1;
        assert!(self.attempt <= 2);
        self.state = Arc::new(AtomicU8::new(ACTIVE));
        let software = self.attempt == 2;
        println!(
            "GRAPHICS_ATTEMPT generation={} policy={}",
            self.generation,
            if software { "cpu" } else { "preferred" }
        );
        let prefer_hardware = std::env::var("IFW_QA_GRAPHICS").as_deref() == Ok("init-fallback");
        let WgpuSetup::CreateNew(setup) = &mut options.wgpu_options.wgpu_setup else {
            unreachable!()
        };
        #[cfg(target_os = "windows")]
        if !software && !prefer_hardware {
            // Keep the system's default DX12 adapter selection for ordinary Windows startup.
            return;
        }
        #[cfg(target_os = "linux")]
        let mailbox = Arc::clone(&self.mesa_mailbox);
        setup.native_adapter_selector = Some(Arc::new(move |adapters, surface| {
            // Rejecting an absent preferred device here exercises the real eframe initialization error.
            let supported = || {
                adapters
                    .iter()
                    .filter(|a| surface.is_none_or(|s| a.is_surface_supported(s)))
            };
            let hardware = || {
                supported().find(|a| {
                    matches!(
                        a.get_info().device_type,
                        wgpu::DeviceType::IntegratedGpu
                            | wgpu::DeviceType::DiscreteGpu
                            | wgpu::DeviceType::VirtualGpu
                    )
                })
            };
            let cpu = || supported().find(|a| a.get_info().device_type == wgpu::DeviceType::Cpu);
            let selected = if software {
                cpu()
            } else if prefer_hardware {
                hardware()
            } else {
                hardware().or_else(cpu).or_else(|| supported().next())
            };
            #[cfg(target_os = "linux")]
            if let Some(adapter) = selected {
                let info = adapter.get_info();
                let has_mode = info.backend == wgpu::Backend::Vulkan
                    && info.device_type == wgpu::DeviceType::Cpu
                    && info.driver.eq_ignore_ascii_case("llvmpipe")
                    && info.driver_info.starts_with("Mesa ")
                    && surface.is_some_and(|s| {
                        s.get_capabilities(adapter)
                            .present_modes
                            .contains(&wgpu::PresentMode::Mailbox)
                    });
                mailbox.store(has_mode, Ordering::Release);
            }
            selected
                .cloned()
                .ok_or_else(|| "No compatible adapter for this native graphics attempt".to_owned())
        }));
    }

    pub(super) fn attach(&mut self, creation: &eframe::CreationContext<'_>) {
        #[cfg(target_os = "linux")]
        {
            use winit::raw_window_handle::{HasWindowHandle, RawWindowHandle};
            self.change_surface_mode = self.mesa_mailbox.load(Ordering::Acquire)
                && creation
                    .winit_window()
                    .and_then(|w| w.window_handle().ok())
                    .is_some_and(|h| matches!(h.as_raw(), RawWindowHandle::Wayland(_)));
        }
        let render = creation
            .wgpu_render_state
            .as_ref()
            .expect("wgpu render state");
        let state = Arc::clone(&self.state);
        let generation = self.generation;
        let wake = creation.winit_window().map(Arc::downgrade);
        render.device.set_device_lost_callback(move |reason, _| {
            if state
                .compare_exchange(ACTIVE, LOST, Ordering::AcqRel, Ordering::Acquire)
                .is_ok()
            {
                println!("GRAPHICS_LOST generation={generation} reason={reason:?}");
                if let Some(w) = wake.as_ref().and_then(|window| window.upgrade()) {
                    w.request_redraw();
                }
            }
        });
        self.device = Some(render.device.clone());
        println!("GRAPHICS_READY generation={generation}");
    }

    pub(super) fn apply_surface_choice(&mut self, frame: &mut eframe::Frame) {
        // The frozen IME probe loses its Wayland text input on Mesa's software FIFO path.
        // Change only an actual llvmpipe Wayland surface that advertised Mailbox for this adapter.
        if std::mem::take(&mut self.change_surface_mode)
            && let Some(mut config) = frame.wgpu_surface_config()
        {
            config.present_mode = wgpu::PresentMode::Mailbox;
            frame.set_wgpu_surface_config(config);
            println!(
                "GRAPHICS_PRESENT generation={} mode=Mailbox driver=llvmpipe desktop=Wayland",
                self.generation
            );
        }
    }

    pub(super) fn request_test_fault(&mut self) {
        if self.fault_on_paint {
            self.queued_fault = true;
        } else {
            self.destroy();
        }
    }

    pub(super) fn finish_ui_for_test(&mut self) {
        if std::mem::take(&mut self.queued_fault) {
            assert!(!self.unrelated, "Unrelated UI test failure");
            println!("GRAPHICS_IN_PAINT generation={}", self.generation);
            self.destroy();
        }
    }

    fn destroy(&self) {
        if let Some(device) = &self.device {
            println!("GRAPHICS_DESTROY generation={}", self.generation);
            device.destroy();
            let _ = device.poll(wgpu::PollType::Wait {
                submission_index: None,
                timeout: Some(Duration::from_secs(2)),
            });
        }
    }

    pub(super) fn lost(&self) -> bool {
        !self.raw && self.state.load(Ordering::Acquire) == LOST
    }

    pub(super) fn drain_lost_device(&self) {
        if self.lost()
            && let Some(device) = &self.device
        {
            // The failed submit may still own an acquired surface texture. Give wgpu
            // a bounded turn to release invalid GPU resources before dropping the surface.
            let result = device.poll(wgpu::PollType::Wait {
                submission_index: None,
                timeout: Some(Duration::from_millis(500)),
            });
            println!(
                "GRAPHICS_DRAIN generation={} result={result:?}",
                self.generation
            );
        }
    }

    pub(super) fn finish(&mut self, failed: bool) -> bool {
        let lost = self.state.swap(RELEASED, Ordering::AcqRel) == LOST;
        self.device = None;
        if failed {
            self.last_failure = Some(if lost {
                Failure::DeviceLost
            } else {
                Failure::Initialization
            });
        }
        if failed && self.attempt < 2 {
            println!("GRAPHICS_RETRY generation={}", self.generation);
            return true;
        }
        if failed {
            println!("GRAPHICS_UNAVAILABLE attempts={}", self.attempt);
        }
        self.attempt = 0;
        false
    }

    pub(super) fn notice(&self, german: bool) -> Option<&'static str> {
        self.last_failure.map(|cause| match (cause, german) {
            (Failure::DeviceLost, true) => {
                "Grafikgerät verloren. Die Anzeige wurde wiederhergestellt."
            }
            (Failure::DeviceLost, false) => "Graphics device lost. The display was restored.",
            (Failure::Initialization, true) => {
                "Grafikstart fehlgeschlagen. Die Anzeige wurde wiederhergestellt."
            }
            (Failure::Initialization, false) => {
                "Graphics initialization failed. The display was restored."
            }
        })
    }
}
