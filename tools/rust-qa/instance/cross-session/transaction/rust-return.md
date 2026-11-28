# Returning a Rust-written profile to the installed Windows editor

This optional Windows x64 trial follows the [private MSI transaction](../installed-writer.md#private-msi-transaction-for-the-original-x64-launch-paths).
It checks what the reinstalled 3.0.4 WPF editor reads from a profile returned
by the feasibility harness. The YAML writer ran earlier on Windows x64.
Its [original archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234228)
records producer revision `0bb39bff547b649e4b4f4bf7647e8cbd1b91fe47`,
the executable digest and the two complete documents.

On the disposable x64 guest, put the original Windows AMD64 YAML ZIP on
the private DVD as `yaml.zip`. Its SHA-256 is
`5694b3ee33b8709ac80bc535759df60cbfefa95d6594945579e3480f9e4a450b`.
Use the usual administrator transaction and add `--rust-yaml-return` to
the ordinary RDP user's [transaction command](../installed-writer.md#reproducing-the-transaction).
This input has no server address or API key.

The ordinary user stages a new profile copy after the committed upgrade
and its writer veto. It contains the original synthetic database, WAL and
SHM plus the changed native Rust document. The original four-file donor is
kept separately throughout the trial. Once the original MSI has been
reinstalled, the test starts the registered WPF executable against
the copy. Windows UI Automation identifies the folder page, its one source
and the General tab on the visible WPF window. The observer checks the
native hit against the window and reads the album through the field's
UI Automation peer when available. The measured WPF tab exposes its
container at the album coordinates. In that case the observer captures
the complete native window and compares the album field with the original
Windows reference. It records the observed method, window handle, process
creation time and RDP session. After normal tray Quit the test archives the
copy and returns the four original files.

The image reference comes from a separate original guest archive. Its
WPF process copied the exact album text and owned the new clipboard value.
The earlier observer stopped after reading that text when its check on
clipboard ownership and sequence failed. A second native run produced the
same full screenshot. On the two 1080 × 760 images the same 236 × 37 RGB
region, starting at window coordinates (454, 394), contains the complete
album. Its SHA-256 is
`7181b9d5d68560c9e75f52c349f033a299c5f038aef23a89271adbb86bff6bb6`.
Detached replay verifies the reference archive, the earlier WPF text
receipt and both crops. A one-pixel change to the returned album field
failed replay. The successful path can read the pixels without using the
guest clipboard.

The reference ZIP is
`artifacts/rust/local-windows-server-2025-x64/20261128/cutover-yaml-89e019d/share/original-guest.zip`,
SHA-256 `ce9de4337ed2f7cca54a8029bd569768ea8a7dba3854ddb203b803d492b761a7`.


The detached reader also checks the MSI transaction and the original and
edited documents against the native writer archive.

```sh
python3 -B tools/rust-qa/instance/cross-session/transaction/replay_return.py \
  share/original-guest.zip disc/endpoint.zip disc/handover.zip \
  disc/checkout.zip disc/yaml.zip "$reference_zip"
```

## Local Windows x64 result

The standard user's RDP session 2 ran observer
`cc1651b6b867fb1876373038b2d3c1d8c1583be4` on Server 2025 x64 with 3072
MiB. The restored WPF editor, PID 2604 and HWND 197052, showed one source.
The original screenshot displayed the folder `Fotos 日本語` and album
`Rust – Grüße 日本語 😀: # null`. The UI Automation hit on this field
belonged to the tab on PID 2604; the album readback used the matching
native pixels. Windows Installer restored its previous installation
during the deliberately failed attempt (1603). The subsequent upgrade,
private MSI removal and original reinstall each returned 0. After the
upgrade the private preflight returned 21 and the original WPF executable
was absent.

The installed 3.0.4 editor exited through its own tray Quit. Its 607-byte
config copy still had SHA-256
`6ab08acb18046139ddeee1aa46c8bb7e7ebb4fcd9a8d637108236d162bc6a654`.
The SQLite database, WAL and SHM in that copy each retained the original
digest. The original four-file profile was returned intact, including its
441-byte config with SHA-256
`601aaf68c3c3785227866759f4257b10d8c1c72776aef83e75ecfba1527d81cc`.
The previously archived Rust writer supplied the configuration bytes.
This trial covers readback by installed WPF with the private successor's
write veto still in force.

The original, 999,354-byte guest ZIP has SHA-256
`e3629c9b947ae348ec15e8d5b33c49c34af34f11ce861d7d774da611ae5348b6`.
It is under
`artifacts/rust/local-windows-server-2025-x64/20261128/cutover-yaml-cc1651b/share/original-guest.zip`.
`rust-return/returned-window.png`, `rust-return/uia.json` and the three
profile receipts are inside. The detached result is `readback.json`
beside the input DVD and the ACPI shutdown record.
