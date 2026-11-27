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
