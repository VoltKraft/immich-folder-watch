# Reference source notices

The patch is the original `document-portal/document-portal-fuse.c` hunk from
xdg-desktop-portal commit `caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57`, authored by
Sebastian Wick, committed 2026-10-29. The affected file is
SPDX `LGPL-2.1-or-later`, copyright the xdg-desktop-portal contributors (the
1.22.1 file credits Red Hat, Inc. and GNOME Foundation Inc.). The upstream
repository and unmodified release archive remain the authoritative source:

- <https://github.com/flatpak/xdg-desktop-portal>
- <https://github.com/flatpak/xdg-desktop-portal/releases/tag/1.22.1>
- <https://github.com/flatpak/xdg-desktop-portal/commit/caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57>

The unchanged upstream license text is retained as
[LICENSE.upstream-LGPL-2.1.txt](LICENSE.upstream-LGPL-2.1.txt).

The recipe preserves the complete release source and all its notices. Portal
translation units and generated D-Bus source inputs use LGPL-2.1-or-later or the
upstream project license. The project Meson declaration is LGPL-2.0-or-later;
individual file notices take precedence. The bundled libglnx has LGPL-2.0-or-later
and LGPL-2.1-or-later code, including systemd-derived lockfile code, and retained
test notices. GVDB code is LGPL-2.1-or-later. The exact bundled source revisions
are recorded in the release archive's wrap files and the evidence document.

The signed Fedora FUSE header/runtime RPMs declare LGPL-2.1-or-later and preserve
`usr/share/licenses/fuse3-libs/LGPL2.txt`. They are extracted privately, not
installed or redistributed. SDK and host libraries remain external installed
development/runtime inputs; generated per-run inventory records the actual host
library bytes and RPM license declarations. This experiment neither adopts
these sources into the Rust application nor establishes release compliance for a
redistributable portal package. Any later distribution requires preserving the
source, modifications, notices, applicable license texts and relinking rights.
