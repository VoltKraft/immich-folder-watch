# Installation on Linux

## Prerequisites

- Linux distribution with `systemd` (for service mode)
- .NET SDK 8.0+ (for source-based run/build)
- Immich server URL and API key

## Console Mode

```bash
cp examples/config.example.yml config.yml
# Edit config.yml

dotnet restore
dotnet build ImmichFolderWatch.sln -c Release
dotnet run --project src/ImmichFolderWatch.Daemon -- --config config.yml
```

## systemd Unit Template

Create `/etc/systemd/system/immich-folder-watch.service`:

```ini
[Unit]
Description=Immich Folder Watch Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/immich-folder-watch
ExecStart=/usr/bin/dotnet /opt/immich-folder-watch/ImmichFolderWatch.Daemon.dll --config /etc/immich-folder-watch/config.yml
Restart=always
RestartSec=5
User=immichwatch
Group=immichwatch

[Install]
WantedBy=multi-user.target
```

Then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now immich-folder-watch
sudo systemctl status immich-folder-watch
```
