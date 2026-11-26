use super::*;
use eframe::App as _;
use egui::epaint::Primitive;
use egui::{Pos2, RawInput, Rect, TextureId, Vec2, ViewportId};
use std::collections::BTreeSet;

#[test]
fn actual_view_mesh_and_texture_requests() {
    for scale in [1.0_f32, 1.5] {
        let mut gpu = view_gpu_reference::Reference::new();
        let mut cpu = [true, false].map(|cache| {
            cpu_painter::EguiSoftwareRender::new(cpu_painter::ColorFieldOrder::Bgra)
                .with_caching(cache)
        });
        let ctx = egui::Context::default();
        ctx.enable_accesskit();
        let creation = eframe::CreationContext::_new_kittest(ctx.clone());
        let mut frame = eframe::Frame::_new_kittest();
        let (sender, commands) = mpsc::sync_channel(8);
        let control = Control {
            sender,
            window: Default::default(),
            graphics_attention: Default::default(),
            appearance: Default::default(),
        };
        let model = Rc::new(RefCell::new(Model {
            lifecycle: DesktopLifecycle::new(false),
            commands,
            filename: "Grüße – Sommer.jpg".into(),
            password: String::new(),
            german: true,
            passes: 0,
            graphics: graphics::Graphics::new(),
            last_focus: None,
            restore_focus: false,
        }));
        let mut window = Window::new(&creation, model.clone(), control);
        for (index, (de, name)) in [
            (true, "Grüße – Sommer.jpg"),
            (false, "東京 – صورة.png"),
            (true, "Grüße – Sommer.jpg"),
        ]
        .into_iter()
        .enumerate()
        {
            model.borrow_mut().german = de;
            model.borrow_mut().filename = name.into();
            model.borrow_mut().password = "synthetic".into();
            let mut input = RawInput {
                screen_rect: Some(Rect::from_min_size(Pos2::ZERO, Vec2::new(640.0, 400.0))),
                time: Some(index as f64),
                ..Default::default()
            };
            input
                .viewports
                .get_mut(&ViewportId::ROOT)
                .unwrap()
                .native_pixels_per_point = Some(scale);
            let mut output = ctx.run_ui(input, |ui| window.ui(ui, &mut frame));
            assert_eq!(output.pixels_per_point, scale);
            let jobs = ctx.tessellate(std::mem::take(&mut output.shapes), scale);
            let mut ids = BTreeSet::new();
            let mut triangles = 0;
            let mut classes = [0usize; 4];
            let mut vertices = 0;
            for job in &jobs {
                let Primitive::Mesh(mesh) = &job.primitive else {
                    panic!("Unexpected native paint callback")
                };
                assert!(mesh.is_valid() && job.clip_rect.is_finite());
                for face in mesh.indices.chunks_exact(3) {
                    let [a, b, c] = [face[0], face[1], face[2]].map(|i| &mesh.vertices[i as usize]);
                    let same_uv = a.uv == b.uv && b.uv == c.uv;
                    let same_color = a.color == b.color && b.color == c.color;
                    classes[usize::from(!same_uv) * 2 + usize::from(!same_color)] += 1;
                }
                triangles += mesh.indices.len() / 3;
                vertices += mesh.vertices.len();
                ids.insert(mesh.texture_id);
            }
            assert_eq!(jobs.len(), 5);
            let expected_geometry = if index == 1 {
                (414, 396, [104, 224, 86, 0])
            } else {
                (426, 420, [104, 224, 98, 0])
            };
            assert_eq!((triangles, vertices, classes), expected_geometry);
            assert_eq!(ids, BTreeSet::from([TextureId::Managed(0)]));
            println!(
                "VIEW scale={scale} frame={index} meshes={} triangles={triangles} vertices={vertices} solid={} varying_color={} textured={} textured_varying_color={}",
                jobs.len(),
                classes[0],
                classes[1],
                classes[2],
                classes[3]
            );
            let mut updates = Vec::new();
            for (id, changes) in &output.textures_delta.set {
                for delta in changes {
                    assert_eq!(*id, TextureId::Managed(0));
                    assert_eq!(delta.options, egui::TextureOptions::LINEAR);
                    updates.push((delta.pos, delta.image.size()));
                    println!(
                        "TEXTURE id={id:?} at={:?} size={:?} options={:?}",
                        delta.pos,
                        delta.image.size(),
                        delta.options
                    );
                }
            }
            let expected_updates = match index {
                0 => vec![(None, [2048, 32])],
                1 if scale == 1.0 => vec![(Some([359, 0]), [183, 14])],
                1 => vec![(Some([455, 0]), [249, 19])],
                _ => Vec::new(),
            };
            assert_eq!(updates, expected_updates);
            let pixels = gpu.draw(scale, &jobs, &output.textures_delta);
            std::fs::write(format!("/pixels/view-{scale}-{index}-wgpu.bgra"), pixels).unwrap();
            let width = (640.0 * scale) as usize;
            let height = (400.0 * scale) as usize;
            for (painter, mode) in cpu.iter_mut().zip(["cached", "direct"]) {
                let mut pixels = vec![[0, 0, 0, 255]; width * height];
                let start = std::time::Instant::now();
                painter.render(
                    &mut cpu_painter::BufferMutRef::new(&mut pixels, width, height),
                    &jobs,
                    &output.textures_delta,
                    scale,
                );
                println!(
                    "CPU scale={scale} frame={index} mode={mode} raster_us={}",
                    start.elapsed().as_micros()
                );
                std::fs::write(
                    format!("/pixels/view-{scale}-{index}-{mode}.bgra"),
                    pixels.as_flattened(),
                )
                .unwrap();
            }
            output.textures_delta.clear();
        }
    }
}
