# Screenshots for Flathub listing

`metainfo.xml` references PNG files in this directory. Flathub's
metadata pipeline fetches them at build time (separate from the
Flatpak build itself) and shows them on the app's flathub.org
listing.

## Currently shipped

| File | Caption | Type |
|------|---------|------|
| `GUI.png` | Settings: Immich server, watch sources, per-folder sync mode, and autostart | default (hero) |

Adding more is optional — Flathub allows up to 5-6 useful shots.
For each new file:
1. Drop the PNG into this directory.
2. Add a `<screenshot>` block in `../io.github.voltkraft.immich-folder-watch.metainfo.xml`
   (only one entry should carry `type="default"`).
3. Re-tag (or, before the first tag, just commit alongside the
   release).

## Capture guidelines

- **Resolution**: 1280×720 minimum. Landscape 16:9 preferred but not
  required — settings-heavy apps land portrait fine.
- **Theme**: OS default. Adwaita on GNOME, Breeze on KDE. Heavy
  custom themes look out of place in store listings.
- **Content**: real, non-empty state. Empty windows look abandoned.
- **Privacy**: no real API keys, hostnames, or path structures.
  Use placeholders like `https://immich.example.com/api`.
- **Format**: PNG, 24-bit. No transparency.

## Capture commands

GNOME:
```bash
gnome-screenshot --window --delay=3 --file=GUI.png
```

KDE Plasma:
```bash
spectacle --window --output=GUI.png
```

## Tagged URLs

`metainfo.xml` references screenshots via
`raw.githubusercontent.com/.../v<VERSION>/...`. Use a tag whose
screenshot URL already resolves before running the Flathub repo linter —
no CDN, no separate hosting.

## Verifying

After PNGs are in place AND the matching tag is pushed:

```bash
appstreamcli validate \
    ../io.github.voltkraft.immich-folder-watch.metainfo.xml
```

`screenshot-image-not-found` warnings should disappear.
