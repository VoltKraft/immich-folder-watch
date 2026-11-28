//! Choose a DXGI presentation interval for egui on a software-rendered Windows HWND.
use eframe::wgpu::{Backend, DeviceType, PresentMode};

pub(super) fn choose(
    creation: &eframe::CreationContext<'_>,
    generation: u64,
) -> Option<PresentMode> {
    let render = creation.wgpu_render_state.as_ref()?;
    let adapter = render.adapter.get_info();
    if adapter.backend != Backend::Dx12 || adapter.device_type != DeviceType::Cpu {
        return None;
    }
    // eframe owns its configured surface. A second unconfigured surface for this same HWND
    // queries the selected adapter's capabilities without allocating another swap chain.
    let window = creation.winit_window()?.clone();
    #[cfg(target_arch = "x86_64")]
    if let Some(mode) = std::env::var_os("IFW_QA_DWM_TRANSITIONS") {
        assert_eq!(std::env::var("IFW_QA_ISOLATED").as_deref(), Ok("1"));
        assert_eq!(std::env::var("IFW_QA_BENCHMARK").as_deref(), Ok("1"));
        assert_eq!(generation, 1, "The DWM comparison lost its original device");
        native_gui_assessment::observe_transitions(&window, &mode);
    }
    let surface = match render.instance.create_surface(window) {
        Ok(surface) => surface,
        Err(error) => {
            println!(
                "GRAPHICS_SURFACE generation={generation} desktop=WindowsDx12Cpu error={error}"
            );
            return None;
        }
    };
    let offered = surface.get_capabilities(&render.adapter).present_modes;
    let fifo_control = std::env::var("IFW_QA_ISOLATED").as_deref() == Ok("1")
        && std::env::var("IFW_QA_WINDOWS_PRESENT_CONTROL").as_deref() == Ok("fifo");
    let mode = if fifo_control {
        PresentMode::Fifo
    } else {
        PresentMode::Mailbox
    };
    println!("GRAPHICS_SURFACE generation={generation} desktop=WindowsDx12Cpu offered={offered:?}");
    offered.contains(&mode).then_some(mode)
}

pub(super) fn apply(frame: &mut eframe::Frame, generation: u64, mode: PresentMode) {
    if let Some(mut config) = frame.wgpu_surface_config() {
        config.present_mode = mode;
        if mode == PresentMode::Mailbox
            && std::env::var("IFW_QA_ISOLATED").as_deref() == Ok("1")
            && std::env::var("IFW_QA_WINDOWS_PRESENT_CONTROL").as_deref() == Ok("mailbox-two")
        {
            config.desired_maximum_frame_latency = Some(2);
        }
        frame.set_wgpu_surface_config(config);
        println!(
            "GRAPHICS_PRESENT generation={generation} desktop=WindowsDx12Cpu mode={mode:?} latency={:?}",
            config.desired_maximum_frame_latency
        );
    }
}
