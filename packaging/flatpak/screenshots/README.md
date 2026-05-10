# Screenshots for Flathub listing

The `metainfo.xml` references three PNG files in this directory. They
are fetched by Flathub's metadata pipeline (separate from the build)
and shown on the app's flathub.org listing.

## Required files

| File | Caption | Suggested content |
|------|---------|-------------------|
| `main-window.png` | Configure the Immich server and watched folders | Default settings view: server URL filled in (use a placeholder like `https://immich.example.com/api`, never your real key in the screenshot), one or two source folders listed with album mappings. |
| `sync-modes.png` | Pick a per-folder sync mode | Same window with the SyncMode dropdown opened on a row, showing the three options (UploadNew, UploadAll, Sync). |
| `logging.png` | Logging via journald or rolling files | Logging section visible: LogTarget dropdown open showing Journald + File, log level set to Information. |

## Capture guidelines

- **Resolution**: 1280×720 minimum, 16:9 aspect ratio preferred.
  Screenshots are auto-thumbnailed by Flathub.
- **Theme**: take in the OS default theme — Adwaita on GNOME or
  Breeze on KDE. Avoid heavy custom themes.
- **Content**: show real, non-empty state. Empty windows look
  abandoned in store listings.
- **Privacy**: redact API keys, hostnames, and any path that
  reveals real folder structures. The screenshots are public.
- **Format**: PNG, 24-bit. No transparency.

## Capture commands

GNOME:
```bash
gnome-screenshot --window --delay=3 --file=main-window.png
```

KDE Plasma:
```bash
spectacle --window --output=main-window.png
```

Generic Wayland-portal:
```bash
flatpak run --command=gnome-screenshot org.gnome.Screenshot --interactive
```

## Tagged URLs

The metainfo points at `raw.githubusercontent.com/.../v2.5.0/...`.
After committing the PNGs and tagging `v2.5.0`, the URLs resolve
automatically. No CDN, no separate hosting.

## Verifying

After the PNGs are in place AND the v2.5.0 tag has been pushed, run:

```bash
appstreamcli validate --pedantic \
    packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.metainfo.xml
```

The `screenshot-image-not-found` warnings should disappear.
