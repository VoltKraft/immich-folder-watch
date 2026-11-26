//! Bounded input contract for the private full-view CPU painter.
use std::{collections::BTreeMap, io};

use cpu_painter::{BufferMutRef, ColorFieldOrder, EguiSoftwareRender};
use egui::{ClippedPrimitive, Color32, ImageData, TextureId, TextureOptions, TexturesDelta};

const MAX_TEXTURE_PIXELS: usize = 8 * 1024 * 1024;
const MAX_TEXTURES: usize = 64;
const MAX_DELTAS: usize = 256;
const MAX_VERTICES: usize = 131_072;
const MAX_INDICES: usize = 393_216;

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
    fn textures(&mut self, delta: &TexturesDelta, counts: &mut Counts) -> io::Result<()> {
        counts.frees = delta.free.len();
        if delta.set.len() > MAX_TEXTURES || counts.frees > MAX_TEXTURES {
            return Err(io::Error::other("Too many CPU texture IDs in frame"));
        }
        let mut changed_pixels = 0;
        for (id, changes) in &delta.set {
            if !matches!(id, TextureId::Managed(_))
                || changes.is_empty()
                || changes.len() > MAX_DELTAS - counts.sets
            {
                return Err(io::Error::other("Unsupported CPU texture delta batch"));
            }
            counts.sets += changes.len();
            for change in changes {
                let ImageData::Color(image) = &change.image;
                let [w, h] = image.size;
                if w == 0
                    || h == 0
                    || w > 8192
                    || h > 8192
                    || w * h != image.pixels.len()
                    || w * h > MAX_TEXTURE_PIXELS - changed_pixels
                    || change.options != TextureOptions::LINEAR
                {
                    return Err(io::Error::other(
                        "Unsupported CPU texture dimensions, pixels or sampler",
                    ));
                }
                changed_pixels += w * h;
                if let Some([x, y]) = change.pos {
                    let original = self
                        .textures
                        .get(id)
                        .ok_or_else(|| io::Error::other("CPU texture patch without image"))?;
                    if x.checked_add(w).is_none_or(|n| n > original.size[0])
                        || y.checked_add(h).is_none_or(|n| n > original.size[1])
                        || ([x, y] == [0, 0] && image.pixels[0] != original.first)
                    {
                        // This renderer caches the upper-left texel when creating each whole image.
                        return Err(io::Error::other(
                            "CPU texture patch exceeds image or changes cached origin",
                        ));
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
                        return Err(io::Error::other("CPU resident texture budget exceeded"));
                    }
                }
            }
        }
        if !delta.free.iter().all(|id| self.textures.contains_key(id)) {
            return Err(io::Error::other("Unknown CPU texture released"));
        }
        Ok(())
    }

    fn meshes(&self, jobs: &[ClippedPrimitive], scale: f32, counts: &mut Counts) -> io::Result<()> {
        if jobs.len() > 4096 {
            return Err(io::Error::other("Too many CPU primitives"));
        }
        for job in jobs {
            let egui::epaint::Primitive::Mesh(mesh) = &job.primitive else {
                return Err(io::Error::other("Native paint callback outside CPU trial"));
            };
            if !job.clip_rect.is_finite()
                || !self.textures.contains_key(&mesh.texture_id)
                || mesh.vertices.len() > MAX_VERTICES - counts.vertices
                || mesh.indices.len() > MAX_INDICES - counts.indices
                || !mesh.indices.len().is_multiple_of(3)
                || !mesh.is_valid()
            {
                return Err(io::Error::other("Invalid CPU mesh, texture or clip"));
            }
            let mut bounds = egui::Rect::NOTHING;
            for vertex in &mesh.vertices {
                let pos = vertex.pos * scale;
                if !pos.is_finite()
                    || pos.x.abs().max(pos.y.abs()) > 16384.0
                    || !vertex.uv.is_finite()
                    || vertex.uv.x.abs().max(vertex.uv.y.abs()) > 2.0
                {
                    return Err(io::Error::other("CPU mesh has unsupported coordinates"));
                }
                bounds.extend_with(pos);
            }
            if bounds.width().max(bounds.height()) > 8192.0 {
                return Err(io::Error::other(
                    "CPU backend would discard an oversized mesh",
                ));
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
        delta: &mut TexturesDelta,
        scale: f32,
    ) -> io::Result<Counts> {
        if !scale.is_finite() || scale <= 0.0 || scale > 16.0 {
            return Err(io::Error::other("Invalid CPU pixels per point"));
        }
        let mut counts = Counts::default();
        self.textures(delta, &mut counts)?;
        if let Some([w, h]) = size {
            if w == 0
                || h == 0
                || w > 8192
                || h > 8192
                || w * h > 8 * 1024 * 1024
                || !clear.iter().all(|v| (0.0..=1.0).contains(v))
            {
                return Err(io::Error::other(
                    "Unsupported CPU framebuffer or clear color",
                ));
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
        delta.clear();
        Ok(counts)
    }
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
        raster.draw(None, [0.; 4], &[], &mut delta, 1.).unwrap();
        assert!(raster.pixels.is_empty() && delta.is_empty());
        for color in [Color32::GREEN, Color32::RED] {
            delta.push(
                ID,
                ImageDelta::partial([1, 0], image(color, [1, 1]), TextureOptions::LINEAR),
            );
        }
        delta.free(ID);
        let jobs = [quad()];
        let count = raster
            .draw(Some([5, 5]), [0., 0., 1., 1.], &jobs, &mut delta, 2.)
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
        assert!(delta.is_empty());
        assert_eq!(raster.pixels[2 * 5 + 2], [0, 0, 255, 255]);
        assert_eq!(raster.pixels[4 * 5 + 4], [255, 0, 0, 255]);
        assert!(
            raster
                .draw(Some([5, 5]), [0.; 4], &jobs, &mut delta, 2.)
                .is_err()
        );
    }

    #[test]
    fn refuses_unsupported_sampler_origin_patch_and_out_of_bounds_patch() {
        let mut delta = TexturesDelta::default();
        for change in [
            ImageDelta::full(image(Color32::WHITE, [2, 1]), TextureOptions::NEAREST),
            ImageDelta::partial([0, 0], image(Color32::RED, [1, 1]), TextureOptions::LINEAR),
            ImageDelta::partial(
                [usize::MAX, 0],
                image(Color32::RED, [1, 1]),
                TextureOptions::LINEAR,
            ),
        ] {
            let mut raster = Raster::new();
            delta.push(
                ID,
                ImageDelta::full(image(Color32::WHITE, [2, 1]), TextureOptions::LINEAR),
            );
            raster.draw(None, [0.; 4], &[], &mut delta, 1.).unwrap();
            delta.push(ID, change);
            assert!(
                raster
                    .draw(Some([2, 1]), [0.; 4], &[], &mut delta, 1.)
                    .is_err()
            );
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
        assert!(
            raster
                .draw(Some([2, 2]), [0.; 4], &[callback], &mut empty, 1.)
                .is_err()
        );
        for (size, scale) in [([8192, 8192], 1.), ([0, 1], 1.), ([1, 1], f32::NAN)] {
            assert!(
                raster
                    .draw(Some(size), [0.; 4], &[], &mut empty, scale)
                    .is_err()
            );
        }
        empty.push(
            ID,
            ImageDelta::full(image(Color32::WHITE, [2, 1]), TextureOptions::LINEAR),
        );
        raster.draw(None, [0.; 4], &[], &mut empty, 1.).unwrap();
        let mut jobs = [quad()];
        let Primitive::Mesh(mesh) = &mut jobs[0].primitive else {
            unreachable!()
        };
        let original = mesh.indices[0];
        mesh.indices[0] = 99;
        assert!(
            raster
                .draw(Some([2, 2]), [0.; 4], &jobs, &mut empty, 1.)
                .is_err()
        );
        let Primitive::Mesh(mesh) = &mut jobs[0].primitive else {
            unreachable!()
        };
        mesh.indices[0] = original;
        mesh.vertices[0].pos.x = 9001.;
        assert!(
            raster
                .draw(Some([2, 2]), [0.; 4], &jobs, &mut empty, 1.)
                .is_err()
        );
    }
}
