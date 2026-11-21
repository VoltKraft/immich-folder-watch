# RW-02 Ubuntu screen reader

The ordinary Rust filename and password controls produced real Orca speech on X11 and Mutter Wayland in the isolated Ubuntu 24.04.5 x64 userspace. Both runs used Ubuntu's native Mesa, AT-SPI, Speech Dispatcher and eSpeak NG on the local Fedora kernel. The dedicated display, session bus and ALSA file sink were inside the test namespaces. The initial local confirmation covers x64. Ubuntu ARM64 has reviewed package inputs for a separate native execution. [Canonical GUI assessment](rw02-native-gui.md)

## Native observation

The driver establishes an initial focus on the language button and waits for its actual speech. It then moves focus using the native keyboard. Orca must announce the German filename, the password field, the English language button and the translated filename in order. The protected interval must contain three individually spoken bullets. Raw key, character and string events are inspected for the synthetic password characters. The checker authenticates the retained Orca trace, eSpeak module initialization, private ALSA recording and input observations against the same native GUI binary. It requires more than 8,192 additional audio bytes and nonzero samples **after** the measured traversal starts. The checks exercise audible synthesis to a file. [Speech observer](../../tools/rust-qa/gui/screen_reader.py), [keyboard traversal](../../tools/rust-qa/gui/desktop_input.py), [receipt verifier](../../tools/rust-qa/ubuntu-reader/verify.py)

Ubuntu Orca 46.1 reported `English push button.` on the original X11 run. Its first key event had already identified the filename as focused before the focus notification arrived, so it omitted that announcement. On Wayland the same Orca release unconditionally called `xkbcomp` with `os.environ['DISPLAY']` during modifier initialization and exited. The test gives only that reader process access to the fixture's existing private X server `:93` for the modifier map and explicitly selects GTK's Wayland backend. The Rust client has only the Mutter Wayland display. A private pseudo-terminal supplies line-buffered Orca diagnostics, allowing the driver to wait for the actual utterance before moving focus again. Current Fedora Orca 51.1 uses its normal Wayland environment. [Ubuntu Orca source package](https://packages.ubuntu.com/source/noble/orca)

| Native x64 run | Recorded directory | Non-silent interval, bytes | Spoken mask count |
| --- | --- | ---: | ---: |
| Ubuntu X11 | `ubuntu-reader/runs/x11-u1rhhz12` | 518,238 | 3 |
| Ubuntu Wayland | `ubuntu-reader/runs/wayland-8_j1msv4` | 687,440 | 3 |
| Fedora X11 | `gui-run/x11-3kcw18ei` | 594,430 | 3 |
| Fedora Wayland | `gui-run/wayland-wc2pnfs9` | 624,430 | 3 |

Directories are relative to `artifacts/rust/`. Each reported interval includes both speech samples and gaps, and each passed its non-silence check. All four runs passed the ordinary lifecycle, keyboard, language-switch, masked AT-SPI and clipboard checks. Ubuntu used GUI SHA-256 `a77706470f8dca72751b1cf0ecc3a52520788f21ee96d5a8b0f851799b7c5efe`. Fedora used `80898c73bf97c9d6622ef837cd5361810b041e5d007a1fe742d32ad7921c1002`. Neither run supplied a Mesa presentation override. The 49 retained local receipts cover both originals, four successes, the private recordings and their source metadata. [Local checksum manifest](../../tools/rust-qa/ubuntu-reader/local-x64.sha256)

## Ubuntu test packages

The Noble archive signature used fingerprint `F6ECB3762474EDA9D21B7022871920D1991BC93C`. Its signed SHA-256 list authenticated the amd64 and arm64 package indices. The seven relevant packages were acquired for both targets or as architecture-independent archives. The reviewed pins include archive hashes, package notices and the exact installed reader, dispatcher, Python client, ALSA plugin, eSpeak module, library and English dictionary payloads. The local isolated layer also recorded all 24 additionally resolved amd64 packages and their notices. These are native QA tools. The Rust binary and product distributions do not bundle them. [Reviewed package inputs](../../tools/rust-qa/ubuntu-reader/packages.json), [Ubuntu archive signature](https://archive.ubuntu.com/ubuntu/dists/noble/InRelease)

| QA package | Exact Noble version | Packaged source terms relevant to this test |
| --- | --- | --- |
| `orca` | `46.1-1ubuntu1` | LGPL-2.1-or-later. [Ubuntu Orca package and copyright](https://packages.ubuntu.com/noble/orca) |
| `speech-dispatcher`, `speech-dispatcher-espeak-ng`, `speech-dispatcher-audio-plugins`, `python3-speechd` | `0.12.0~rc2-2build3` | GPL-2.0-or-later for the server and eSpeak module. The audio and Python client sources and shared module helpers have LGPL-2.1-or-later terms. The package notice also describes its documentation and other components. [Ubuntu Speech Dispatcher source](https://packages.ubuntu.com/source/noble/speech-dispatcher) |
| `libespeak-ng1`, `espeak-ng-data` | `1.51+dfsg-12build1` | GPL-3.0-or-later with separately identified permissive source files in the package notice. [Ubuntu eSpeak NG source](https://packages.ubuntu.com/source/noble/espeak-ng) |

After installing the usual native desktop prerequisites on a disposable Noble runner and building the canonical GUI, run each backend independently. The existing Xvfb dependency supplies `xkbcomp`. The two explicit additional apt requests also resolve the dispatcher audio plugin and Python speech client. [Ubuntu eSpeak NG output module](https://packages.ubuntu.com/noble/speech-dispatcher-espeak-ng)

```sh
sudo apt-get install --yes --no-install-recommends \
  orca=46.1-1ubuntu1 speech-dispatcher-espeak-ng=0.12.0~rc2-2build3
python3 tools/rust-qa/gui/native.py --backend x11 --input --screen-reader
python3 tools/rust-qa/gui/native.py --backend wayland --input --screen-reader
python3 tools/rust-qa/ubuntu-reader/verify.py "$NATIVE_TARGET"
```

The last command verifies installed package versions and payloads, replays the two retained speech intervals and writes `artifacts/rust/gui-native/<target>/ubuntu-reader.json`. Keep the usual `gui-run/*/*.json` and `*.log` evidence and the two `gui-run/*/orca-audio.raw` files. The local audit also passed four tests covering exact role names, partially written UTF-8, delivery through the private terminal, synthetic key leakage, a silent measured interval and missing synthesizer initialization.

```sh
python3 -m unittest discover -s tools/rust-qa/ubuntu-reader -v
sha256sum --check tools/rust-qa/ubuntu-reader/local-x64.sha256
```
