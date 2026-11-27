# Installed Flatpak notification on GNOME

The ARM64 job launches GNOME Shell on an isolated Wayland monitor. It installs
the native Rust sender in a temporary Flatpak profile with the signed
freedesktop Platform. The sender posts a fixed title and body, then withdraws
the same notification. The monitor captures the initial desktop, the open
message list and the list after withdrawal. The portal trace identifies the
app, notification ID and backend. The recipient's bus connection belongs to
the process running the private compositor.
[Native workflow](../../../.github/workflows/rust-linux-notification.yaml) ·
[Portal contract and Fedora observations](../../../docs/rust/rw02-portal-dialog.md#notifications-and-autostart).

On GNOME releases that use the GTK portal for notifications, its backend
forwards the identified sender's title and body to GNOME Shell's
`org.gtk.Notifications` service. The recorder follows the sender and receiver
in the actual calls. The three original PNGs and the message-bus trace stay
in the artifact alongside the sender and its source and compiler records.
[GTK forwarding](https://github.com/flatpak/xdg-desktop-portal-gtk/blob/1.15.1/src/notification.c) ·
[GNOME Shell receiver](https://github.com/GNOME/gnome-shell/blob/46.0/js/ui/notificationDaemon.js).

To replay a downloaded artifact, check out its producer revision. Use the
original archive's run and attempt numbers and supply the extracted paths.

```sh
python3 -B tools/rust-qa/portal-dialog/notification_readback.py \
  "$observation_directory" "$native_sender" --arch aarch64 \
  --revision "$revision" --run "$run_id" --attempt "$attempt"
```

The reader checks the original PNG pixels with Pillow, the Tesseract library
and its English model. It requires the full title and body in the middle
capture and a visible message-list control after withdrawal. The native Ubuntu
job records the installed package versions. These are separate QA tools used
on the observer host. Pillow uses a permissive license and Tesseract and its
English data use Apache-2.0. [Pillow license](https://github.com/python-pillow/Pillow/blob/main/LICENSE) ·
[Tesseract license](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE) ·
[English model license](https://github.com/tesseract-ocr/tessdata_fast/blob/main/LICENSE).

## Ubuntu ARM64 capture at 10ab0b8

The installed ARM64 sender submitted and withdrew `native-test`. GTK forwarded
both calls to GNOME Shell PID 13 on the private display. All three screen
captures timed out. GStreamer stopped at PAUSED and WirePlumber 0.4.17
disconnected after failing to start its logind monitor. The detached reader
rejected the missing images. The original archive has 21 members, 2,490,623
bytes and SHA-256
`2eaf33af0a180e86b84594188b6368d54fcf58ec6ec92b1ddba9e53e7f430565`.
[Original ARM64 build and desktop logs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45963591797/artifacts/15181348629).

The same Ubuntu release and WirePlumber package on x64 reproduced the failure
with the original observer. In WirePlumber 0.4 the headless test now disables
the Bluetooth audio and MIDI monitors in its private configuration directory.
It checks that the video session manager has actually connected to PipeWire
before starting GNOME. The repaired x64 trial with the same sender captured
three full frames. The middle frame contained the complete title and body.
After withdrawal the list still showed “Do Not Disturb” and “Clear”.

The local comparison uses the existing Noble userspace on the Fedora x64
kernel. Its original, repaired and ARM64-hosted results are separate. The
repaired x64 capture hashes are
`8bbaca6f54a8ee0d967bfdadf86cf9fb7b6a3707c2e51da7dd8b1d4489846e60`
before posting, `38c55918aa72654bffc52fbbacd6d00c4c35d69a0052d835c09f1a3564ec6cb5`
with the notification visible and
`f46b5b23f2ea53d8455510f73569e631aca24a234cdc506d3315624e37d14d10`
after withdrawal.
