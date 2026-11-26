//! Bounded input contract for the private full-view CPU painter.
use std::{collections::BTreeMap, io};

use cpu_painter::{BufferMutRef, ColorFieldOrder, EguiSoftwareRender};
use egui::{ClippedPrimitive, Color32, ImageData, TextureId, TextureOptions, TexturesDelta};

const MAX_TEXTURE_PIXELS: usize = 8 * 1024 * 1024;
const MAX_TEXTURES: usize = 64;
const MAX_DELTAS: usize = 256;
const MAX_VERTICES: usize = 131_072;
const MAX_INDICES: usize = 393_216;

/// Only a valid draw outside the CPU contract may switch to the normal renderer.
#[derive(Debug)]
pub(crate) enum PaintError {
    Unsupported(&'static str),
    Failure(io::Error),
}

impl From<io::Error> for PaintError {
    fn from(error: io::Error) -> Self {
        Self::Failure(error)
    }
}

fn invalid(message: &'static str) -> PaintError {
    PaintError::Failure(io::Error::other(message))
}

#[derive(Default)]
pub(super) struct Counts {
    pub meshes: usize,
    pub vertices: usize,
    pub indices: usize,
    pub sets: usize,
    pub frees: usize,
}

#[derive(Clone, Copy)]
struct Texture {
    size: [usize; 2],
    first: Color32,
}

pub(super) struct Raster {
    renderer: EguiSoftwareRender,
    textures: BTreeMap<TextureId, Texture>,
    pub pixels: Vec<[u8; 4]>,
}

impl Raster {
    pub(super) fn new() -> Self {
        Self {
            renderer: EguiSoftwareRender::new(ColorFieldOrder::Bgra).with_caching(false),
            textures: BTreeMap::new(),
            pixels: Vec::new(),
        }
    }

    /// Validate whole images and sequential patches in the same per-ID order used by the renderer.
    fn textures(&mut self, delta: &TexturesDelta, counts: &mut Counts) -> Result<(), PaintError> {
        counts.frees = delta.free.len();
        if delta.set.len() > MAX_TEXTURES || counts.frees > MAX_TEXTURES {
            return Err(PaintError::Unsupported("texture-count"));
        }
        let mut changed_pixels = 0;
        for (id, changes) in &delta.set {
            if changes.is_empty() {
                return Err(invalid("Empty CPU texture delta batch"));
            }
            if matches!(id, TextureId::User(_)) {
                return Err(PaintError::Unsupported("user-texture"));
            }
            if changes.len() > MAX_DELTAS - counts.sets {
                return Err(PaintError::Unsupported("texture-count"));
            }
            counts.sets += changes.len();
            for change in changes {
                let ImageData::Color(image) = &change.image;
                let [w, h] = image.size;
                if w == 0 || h == 0 || w.checked_mul(h) != Some(image.pixels.len()) {
                    return Err(invalid("Invalid CPU texture dimensions or pixels"));
                }
                if w > 8192 || h > 8192 || w * h > MAX_TEXTURE_PIXELS - changed_pixels {
                    return Err(PaintError::Unsupported("texture-size"));
                }
                if change.options != TextureOptions::LINEAR {
                    return Err(PaintError::Unsupported("sampler"));
                }
                changed_pixels += w * h;
                if let Some([x, y]) = change.pos {
                    let original = self
                        .textures
                        .get(id)
                        .ok_or_else(|| invalid("CPU texture patch without image"))?;
                    if x.checked_add(w).is_none_or(|n| n > original.size[0])
                        || y.checked_add(h).is_none_or(|n| n > original.size[1])
                    {
                        return Err(invalid("CPU texture patch exceeds its image"));
                    }
                    // The CPU backend caches the upper-left texel of each whole image.
                    if [x, y] == [0, 0] && image.pixels[0] != original.first {
                        return Err(PaintError::Unsupported("texture-origin"));
                    }
                } else {
                    self.textures.insert(
                        *id,
                        Texture {
                            size: [w, h],
                            first: image.pixels[0],
                        },
                    );
                    if self.textures.len() > MAX_TEXTURES
                        || self
                            .textures
                            .values()
                            .map(|t| t.size[0] * t.size[1])
                            .sum::<usize>()
                            > MAX_TEXTURE_PIXELS
                    {
                        return Err(PaintError::Unsupported("texture-size"));
                    }
                }
            }
        }
        if delta.free.iter().any(|id| matches!(id, TextureId::User(_))) {
            return Err(PaintError::Unsupported("user-texture"));
        }
        // TexturesDelta::append can cancel an allocation before any renderer receives it.
        // Both renderers treat freeing an absent managed ID as a no-op.
        Ok(())
    }

    fn meshes(
        &self,
        jobs: &[ClippedPrimitive],
        scale: f32,
        counts: &mut Counts,
    ) -> Result<(), PaintError> {
        if jobs.len() > 4096 {
            return Err(PaintError::Unsupported("primitive-count"));
        }
        for job in jobs {
            let egui::epaint::Primitive::Mesh(mesh) = &job.primitive else {
                return Err(PaintError::Unsupported("callback"));
            };
            if matches!(mesh.texture_id, TextureId::User(_)) {
                return Err(PaintError::Unsupported("user-texture"));
            }
            if mesh.vertices.len() > MAX_VERTICES - counts.vertices
                || mesh.indices.len() > MAX_INDICES - counts.indices
            {
                return Err(PaintError::Unsupported("mesh-size"));
            }
            if !self.textures.contains_key(&mesh.texture_id)
                || !mesh.indices.len().is_multiple_of(3)
                || !mesh.is_valid()
            {
                return Err(invalid("Invalid CPU mesh or missing managed texture"));
            }
            if !job.clip_rect.is_finite() {
                return Err(PaintError::Unsupported("clip"));
            }
            let mut bounds = egui::Rect::NOTHING;
            for vertex in &mesh.vertices {
                let pos = vertex.pos * scale;
                if !pos.is_finite() || !vertex.uv.is_finite() {
                    return Err(invalid("Non-finite CPU mesh vertex"));
                }
                if pos.x.abs().max(pos.y.abs()) > 16384.0
                    || vertex.uv.x.abs().max(vertex.uv.y.abs()) > 2.0
                {
                    return Err(PaintError::Unsupported("mesh-coordinates"));
                }
                bounds.extend_with(pos);
            }
            if bounds.width().max(bounds.height()) > 8192.0 {
                return Err(PaintError::Unsupported("mesh-size"));
            }
            counts.meshes += 1;
            counts.vertices += mesh.vertices.len();
            counts.indices += mesh.indices.len();
        }
        Ok(())
    }

    pub(super) fn draw(
        &mut self,
        size: Option<[usize; 2]>,
        clear: [f32; 4],
        jobs: &[ClippedPrimitive],
        delta: &TexturesDelta,
        scale: f32,
    ) -> Result<Counts, PaintError> {
        if !scale.is_finite() || scale <= 0.0 {
            return Err(invalid("Invalid CPU pixels per point"));
        }
        if scale > 16.0 {
            return Err(PaintError::Unsupported("scale"));
        }
        let mut counts = Counts::default();
        self.textures(delta, &mut counts)?;
        if let Some([w, h]) = size {
            if w == 0 || h == 0 || w > 8192 || h > 8192 || w * h > 8 * 1024 * 1024 {
                return Err(PaintError::Unsupported("dimensions"));
            }
            if !clear.iter().all(|v| (0.0..=1.0).contains(v)) {
                return Err(PaintError::Unsupported("clear-color"));
            }
            self.meshes(jobs, scale, &mut counts)?;
            let [r, g, b, a] = clear.map(|v| (v * 255.0).round() as u8);
            self.pixels.resize(w * h, [0; 4]);
            self.pixels.fill([b, g, r, a]);
            self.renderer.render(
                &mut BufferMutRef::new(&mut self.pixels, w, h),
                jobs,
                delta,
                scale,
            );
        } else if !delta.is_empty() {
            // The initially hidden root still owns its font texture. No real frame is rasterized.
            self.renderer.render(
                &mut BufferMutRef::new(&mut [[0; 4]], 1, 1),
                &[],
                delta,
                scale,
            );
        }
        for id in &delta.free {
            self.textures.remove(id);
        }
        Ok(counts)
    }
}

/// Queue callbacks and screenshot callbacks can read the normal renderer's texture table.
/// Each texture operation releases its renderer lock before the next operation starts.
pub(super) fn finish_frame(
    delta: &mut TexturesDelta,
    upload: impl FnOnce(&mut TexturesDelta),
    submit: impl FnOnce(),
    free: impl FnOnce(&mut TexturesDelta),
    complete: impl FnOnce(),
) {
    if !delta.set.is_empty() {
        upload(delta);
    }
    // The original queue guard also advances unrelated work on an occluded paint call.
    submit();
    if !delta.free.is_empty() {
        free(delta);
    }
    complete();
}

#[cfg(test)]
mod tests {
    use super::*;
    use egui::{
        ColorImage, Mesh, PaintCallback, Rect,
        epaint::{ImageDelta, Primitive},
        pos2,
    };
    use std::sync::Arc;

    const ID: TextureId = TextureId::Managed(0);

    fn image(color: Color32, size: [usize; 2]) -> ColorImage {
        ColorImage::filled(size, color)
    }
    fn quad() -> ClippedPrimitive {
        let mut mesh = Mesh::with_texture(ID);
        let rect = Rect::from_min_max(pos2(0., 0.), pos2(2., 2.));
        // Center of the second texel in a 2x1 image. Both vertices and UVs are genuine mesh input.
        mesh.add_rect_with_uv(
            rect,
            Rect::from_min_max(pos2(0.75, 0.5), pos2(0.75, 0.5)),
            Color32::WHITE,
        );
        ClippedPrimitive {
            primitive: Primitive::Mesh(mesh),
            clip_rect: rect,
        }
    }
    #[test]
    fn hidden_upload_ordered_patches_dpi_bgra_clear_and_post_draw_free() {
        let mut raster = Raster::new();
        let mut delta = TexturesDelta::default();
        delta.push(
            ID,
            ImageDelta::full(image(Color32::WHITE, [2, 1]), TextureOptions::LINEAR),
        );
        raster.draw(None, [0.; 4], &[], &delta, 1.).unwrap();
        assert!(raster.pixels.is_empty() && !delta.is_empty());
        delta.clear();
        for color in [Color32::GREEN, Color32::RED] {
            delta.push(
                ID,
                ImageDelta::partial([1, 0], image(color, [1, 1]), TextureOptions::LINEAR),
            );
        }
        delta.free(ID);
        let jobs = [quad()];
        let count = raster
            .draw(Some([5, 5]), [0., 0., 1., 1.], &jobs, &delta, 2.)
            .unwrap();
        assert_eq!(
            (
                count.sets,
                count.frees,
                count.meshes,
                count.vertices,
                count.indices
            ),
            (2, 1, 1, 4, 6)
        );
        assert!(delta.set[&ID].len() == 2 && delta.free.contains(&ID));
        delta.clear();
        assert_eq!(raster.pixels[2 * 5 + 2], [0, 0, 255, 255]);
        assert_eq!(raster.pixels[4 * 5 + 4], [255, 0, 0, 255]);
        assert!(
            raster
                .draw(Some([5, 5]), [0.; 4], &jobs, &delta, 2.)
                .is_err()
        );
    }

    #[test]
    fn layout_passes_cancel_an_allocation_before_the_hidden_renderer_sees_it() {
        let mut first = TexturesDelta::default();
        first.push(
            ID,
            ImageDelta::full(image(Color32::WHITE, [2, 1]), TextureOptions::LINEAR),
        );
        let mut later = TexturesDelta::default();
        later.free(ID);
        first.append(later);
        assert!(first.set.is_empty() && first.free.contains(&ID));
        let mut raster = Raster::new();
        let counts = raster.draw(None, [0.; 4], &[], &first, 1.).unwrap();
        assert_eq!((counts.sets, counts.frees), (0, 1));
        assert!(raster.pixels.is_empty());
        first.clear();
    }

    #[test]
    fn queue_and_screenshot_callbacks_see_ordered_texture_lifetimes_without_a_write_lock() {
        use std::sync::{
            Arc, Mutex,
            atomic::{AtomicUsize, Ordering},
        };
        let retained = TextureId::Managed(11);
        let freed = TextureId::Managed(12);
        let state = Arc::new(Mutex::new(BTreeMap::from([(freed, Color32::RED)])));
        let observed = Arc::new(AtomicUsize::new(0));
        let callback_state = state.clone();
        let callback_count = observed.clone();
        let screenshot = egui::ScreenshotCallback::new(move |_| {
            assert_eq!(
                *callback_state.try_lock().unwrap(),
                BTreeMap::from([(retained, Color32::GREEN)])
            );
            assert_eq!(callback_count.fetch_add(1, Ordering::SeqCst), 1);
        });
        let mut delta = TexturesDelta::default();
        delta.push(
            retained,
            ImageDelta::full(image(Color32::GREEN, [1, 1]), TextureOptions::LINEAR),
        );
        delta.free(freed);
        finish_frame(
            &mut delta,
            |updates| {
                let mut textures = state.lock().unwrap();
                for (id, changes) in updates.set.drain() {
                    for change in changes {
                        let ImageData::Color(image) = change.image;
                        textures.insert(id, image.pixels[0]);
                    }
                }
            },
            || {
                assert_eq!(
                    *state.try_lock().unwrap(),
                    BTreeMap::from([(retained, Color32::GREEN), (freed, Color32::RED)])
                );
                assert_eq!(observed.fetch_add(1, Ordering::SeqCst), 0);
            },
            |updates| {
                let mut textures = state.lock().unwrap();
                for id in updates.free.drain() {
                    textures.remove(&id);
                }
            },
            || screenshot.complete(Arc::new(image(Color32::WHITE, [1, 1]))),
        );
        assert_eq!(observed.load(Ordering::SeqCst), 2);
        assert!(delta.is_empty());
        // A real empty paint can still release an external queue callback. There is no timer.
        let mut submits = 0;
        finish_frame(
            &mut delta,
            |_| unreachable!(),
            || submits += 1,
            |_| unreachable!(),
            || {},
        );
        assert_eq!(submits, 1);
    }

    #[test]
    fn refuses_unsupported_sampler_origin_patch_and_out_of_bounds_patch() {
        let mut delta = TexturesDelta::default();
        for (change, reason) in [
            ImageDelta::full(image(Color32::WHITE, [2, 1]), TextureOptions::NEAREST),
            ImageDelta::partial([0, 0], image(Color32::RED, [1, 1]), TextureOptions::LINEAR),
            ImageDelta::partial(
                [usize::MAX, 0],
                image(Color32::RED, [1, 1]),
                TextureOptions::LINEAR,
            ),
        ]
        .into_iter()
        .zip([Some("sampler"), Some("texture-origin"), None])
        {
            let mut raster = Raster::new();
            delta.push(
                ID,
                ImageDelta::full(image(Color32::WHITE, [2, 1]), TextureOptions::LINEAR),
            );
            raster.draw(None, [0.; 4], &[], &delta, 1.).unwrap();
            delta.clear();
            delta.push(ID, change);
            let mut expected = delta.clone();
            let result = raster.draw(Some([2, 1]), [0.; 4], &[], &delta, 1.);
            match (result, reason) {
                (Err(PaintError::Unsupported(actual)), Some(reason)) => assert_eq!(actual, reason),
                (Err(PaintError::Failure(error)), None) => {
                    assert_eq!(error.to_string(), "CPU texture patch exceeds its image")
                }
                _ => panic!("Invalid input or CPU fallback was misclassified"),
            }
            assert!(raster.pixels.is_empty());
            assert_eq!(delta, expected);
            expected.clear();
            delta.clear();
        }
    }

    #[test]
    fn refuses_callbacks_invalid_frame_dimensions_dpi_and_invalid_geometry() {
        let mut raster = Raster::new();
        let mut empty = TexturesDelta::default();
        let cb = PaintCallback {
            rect: Rect::ZERO,
            callback: Arc::new(()),
        };
        let callback = ClippedPrimitive {
            primitive: Primitive::Callback(cb),
            clip_rect: Rect::ZERO,
        };
        assert!(matches!(
            raster.draw(Some([2, 2]), [0.; 4], &[callback], &empty, 1.),
            Err(PaintError::Unsupported("callback"))
        ));
        for (size, scale) in [([8192, 8192], 1.), ([0, 1], 1.), ([1, 1], f32::NAN)] {
            assert!(
                raster
                    .draw(Some(size), [0.; 4], &[], &empty, scale)
                    .is_err()
            );
        }
        empty.push(
            ID,
            ImageDelta::full(image(Color32::WHITE, [2, 1]), TextureOptions::LINEAR),
        );
        raster.draw(None, [0.; 4], &[], &empty, 1.).unwrap();
        empty.clear();
        let mut jobs = [quad()];
        let Primitive::Mesh(mesh) = &mut jobs[0].primitive else {
            unreachable!()
        };
        let original = mesh.indices[0];
        mesh.indices[0] = 99;
        assert!(
            raster
                .draw(Some([2, 2]), [0.; 4], &jobs, &empty, 1.)
                .is_err()
        );
        let Primitive::Mesh(mesh) = &mut jobs[0].primitive else {
            unreachable!()
        };
        mesh.indices[0] = original;
        mesh.vertices[0].pos.x = 9001.;
        assert!(
            raster
                .draw(Some([2, 2]), [0.; 4], &jobs, &empty, 1.)
                .is_err()
        );
    }
}
