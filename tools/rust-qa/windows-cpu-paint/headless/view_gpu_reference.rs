use eframe::egui::{ClippedPrimitive, TexturesDelta};
use eframe::egui_wgpu::{Renderer, RendererOptions, ScreenDescriptor};
use std::{sync::mpsc, time::Duration};

pub struct Reference {
    device: wgpu::Device,
    queue: wgpu::Queue,
    renderer: Renderer,
}

impl Reference {
    pub fn new() -> Self {
        let instance = wgpu::Instance::default();
        let adapter = futures_lite::future::block_on(instance.request_adapter(
            &wgpu::RequestAdapterOptions {
                force_fallback_adapter: true,
                ..Default::default()
            },
        ))
        .unwrap();
        let info = adapter.get_info();
        assert_eq!(info.backend, wgpu::Backend::Vulkan);
        assert_eq!(info.device_type, wgpu::DeviceType::Cpu);
        println!(
            "REFERENCE {:?} {:?} {}",
            info.backend, info.device_type, info.name
        );
        let (device, queue) =
            futures_lite::future::block_on(adapter.request_device(&Default::default())).unwrap();
        let renderer = Renderer::new(
            &device,
            wgpu::TextureFormat::Bgra8Unorm,
            RendererOptions::default(),
        );
        Self {
            device,
            queue,
            renderer,
        }
    }

    pub fn draw(
        &mut self,
        scale: f32,
        jobs: &[ClippedPrimitive],
        changes: &TexturesDelta,
    ) -> Vec<u8> {
        let width = (640.0 * scale) as u32;
        let height = (400.0 * scale) as u32;
        assert_eq!(width * 4 % wgpu::COPY_BYTES_PER_ROW_ALIGNMENT, 0);
        let size = wgpu::Extent3d {
            width,
            height,
            depth_or_array_layers: 1,
        };
        let frame = self.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("reference BGRA"),
            size,
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Bgra8Unorm,
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::COPY_SRC,
            view_formats: &[],
        });
        let buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("reference readback"),
            size: u64::from(width * height * 4),
            usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
            mapped_at_creation: false,
        });
        for (id, updates) in &changes.set {
            for delta in updates {
                self.renderer
                    .update_texture(&self.device, &self.queue, *id, delta);
            }
        }
        let desc = ScreenDescriptor {
            size_in_pixels: [width, height],
            pixels_per_point: scale,
        };
        let view = frame.create_view(&Default::default());
        let mut encoder = self.device.create_command_encoder(&Default::default());
        let extras =
            self.renderer
                .update_buffers(&self.device, &self.queue, &mut encoder, jobs, &desc);
        assert!(extras.is_empty());
        let attach = [Some(wgpu::RenderPassColorAttachment {
            view: &view,
            resolve_target: None,
            depth_slice: None,
            ops: wgpu::Operations {
                load: wgpu::LoadOp::Clear(wgpu::Color::BLACK),
                store: wgpu::StoreOp::Store,
            },
        })];
        {
            let mut pass = encoder
                .begin_render_pass(&wgpu::RenderPassDescriptor {
                    color_attachments: &attach,
                    ..Default::default()
                })
                .forget_lifetime();
            self.renderer.render(&mut pass, jobs, &desc);
        }
        encoder.copy_texture_to_buffer(
            frame.as_image_copy(),
            wgpu::TexelCopyBufferInfo {
                buffer: &buffer,
                layout: wgpu::TexelCopyBufferLayout {
                    offset: 0,
                    bytes_per_row: Some(width * 4),
                    rows_per_image: None,
                },
            },
            size,
        );
        let submission = self.queue.submit([encoder.finish()]);
        let slice = buffer.slice(..);
        let (tx, rx) = mpsc::sync_channel(1);
        slice.map_async(wgpu::MapMode::Read, move |r| {
            tx.send(r).unwrap();
        });
        self.device
            .poll(wgpu::PollType::Wait {
                submission_index: Some(submission),
                timeout: Some(Duration::from_secs(5)),
            })
            .unwrap();
        rx.recv_timeout(Duration::from_secs(1)).unwrap().unwrap();
        let pixels = slice.get_mapped_range().unwrap().to_vec();
        for id in &changes.free {
            self.renderer.free_texture(id);
        }
        pixels
    }
}
