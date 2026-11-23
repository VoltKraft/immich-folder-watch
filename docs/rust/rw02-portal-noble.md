# Ubuntu Noble Documents portal file locks

The released Ubuntu 24.04 package `xdg-desktop-portal 1.18.4-1ubuntu2.24.04.3` refused cooperative file locking on a private Documents grant. Both the shipping C# reader and the Rust filesystem reader received `ENOSYS`. Building the exact Ubuntu sources produced the same result. Applying upstream's single `xdp_fuse_flock` function let both readers acquire shared leases and excluded a consenting exclusive writer across the backing and FUSE views. The local execution used native x86-64 Ubuntu 24.04.5 userspace on Fedora kernel `7.3.4-300.fc45.x86_64`. Native Ubuntu x64 and ARM64 subsequently reproduced all three outcomes on their own kernels. Availability of a supported Ubuntu package that implements this capability remains open. [Ubuntu package and source](https://packages.ubuntu.com/noble-updates/xdg-desktop-portal) · [Upstream change](https://github.com/flatpak/xdg-desktop-portal/commit/caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57).

The [installed Noble VM experiment](../../tools/rust-qa/portal-noble/installed/README.md)
tests package installation and rollback with the distro services and a real
Flatpak application identity. Its scope is feasibility. Distribution approval
and any commitment to maintaining an Ubuntu host package remain open.

## Native observations

### Installing the portal package on an offline Noble guest

Canonical's signed October 17 Ubuntu 24.04.5 image booted on native x64
KVM with kernel `6.8.0-147-generic`. Its original package database has
SHA-256 `451a1e0514c959eb18ee94501a025f7728fea601502274ab6a86a67870305cf6`.
Independent readback matched the image signature, all four Ubuntu source
objects and every archive in the 204-package build plan and the separate
23-package runtime plan. Two source reconstructions yielded the same
private DSC and complete patched tree. The build keeps its source and
binary packages in the private test directory. [Canonical image](https://cloud-images.ubuntu.com/noble/20261017/)
· [Reconstruction recipe](../../tools/rust-qa/portal-noble/installed/package/README.md).

In build `package-gvrofrns`, native compilation completed. The distribution
test runner passed 28 of 29 suites. Its location test timed out waiting for
GeoClue to return a client after 25 seconds. Debian packaging stopped at
that test. The original `package-result.json` has SHA-256
`cbedc88a7830c27781179e5253c945edbc6cac1584fe0fa39c97c7b58e72efc6`.

In build `package-0eeh793w` the Ubuntu GeoClue agent used a synthetic static
location on the offline guest. All 29 distribution suites passed and dpkg
built the native runtime, development and installed-test packages and
the two debug packages. The verifier then rejected a different GNU build
ID after Debian debug processing. The original failed report SHA-256 is
`cbe001f5ebdc5ea4753201b9ecb86261452fbcc22f09c62d7c7f1adbd0926032`.
The complete package and test archive SHA-256 is
`81d6a03f131c28a410b6219ef2a9476222476ee1d2db799fd067e88f4a5b7c67`.

In the first stock guest, `lease-stock-t02f_zvn`, the regular user installed
Flathub's signed x64 Platform and the synthetic app. Both live D-Bus services
matched the stock package. Documents refused the export descriptor before
the app could request a lease. Noble's descriptor validation rejects
`O_PATH | O_NOFOLLOW`. The corrected exporter pins the original directory
with those flags, reopens its own pinned descriptor with `O_PATH | O_DIRECTORY`
and verifies the identity before passing it to AddFull. The failed observation
hash is `9f527b263b8358569f5f3290d9c1caf8e2bae0a53dac469a69b3135bf22dde18`.
[Original source and guest commands](../../tools/rust-qa/portal-noble/installed/README.md).

In `lease-stock-g8_tjhbs` the installed app ran as UID 1000. The stock
portal granted the synthetic directory. The app verified its own identity
and FUSE mount and observed `ENOENT` on the direct backing pathname.
A separate shared-lock call in the sandbox returned errno 38. The workspace
Rust reader also returned errno 38 before, during and after an exclusive
backing writer. After revocation it could no longer open the grant.
The service listing confirmed deletion and the original 25 bytes survived
with the same device and inode. The stock and outer result SHA-256 values
are `7f6b80f025ef33bfd285b2118c38487a5a2afbee7e6b599c0c2bf9d462a8f2e8`
and `2f5c627a087f9bc9bc9c931a6a029165ef74b0da4e74c4fb8035ac1dfdf80c95`.

Offline readback of the unmodified `package-0eeh793w` build disk verified
all five packages, both dpkg records and the installed daemon's split debug
file. Ubuntu's debhelper invokes debugedit with a build-ID seed. All 27
allocated ELF sections matched the linked executable after accounting for
the 20 build-ID bytes in the GNU note. The final debug file shared the
packaged build ID `17772f7047be161dbdd206f233c15a10418612ab`. The package
SHA-256 is `1e5f691467d7d6ada852983b875419410a42ef2c525f95e2f70c44ca5c937e50`.
The separate readback SHA-256 is
`eaac90b94f55c15b159df5641abc5a7c764dcbe67c0ca386203d850c0a7d0596`.
[Debian package checks](../../tools/rust-qa/portal-noble/installed/package/README.md).

#### Installed patch and rollback on the same native guest

In `lease-k28ki_zl`, APT installed the verified private package
`1.18.4-1ubuntu2.24.04.3+ifwqa1` and subsequently downgraded it to the
exact original Ubuntu package. A single ordinary user ran the same installed
Flatpak against both D-Bus services at each phase.

| Installed package | Direct shared-lock call in the Flatpak | Workspace Rust reader and competing backing writer | Phase result SHA-256 |
| --- | --- | --- | --- |
| Ubuntu original | errno 38 | The reader returned errno 38 before, during and after the writer | `78b7aecbb334e768858df7dffc30245414347ef13ef5a5d76fccbda942f660cc` |
| Installed backport | Acquired | A held Rust reader excluded the writer with errno 11. A held writer excluded the reader. After release the same reader code reacquired the original file identity and 25 bytes | `68f1a6eb7da19364d5ea2e1d20c94b8a5341ce240e4dcb2990fad30eb24af8f1` |
| Restored Ubuntu original | errno 38 | The reader again returned errno 38 in all three observations | `09df3794bc8e72978fe6307a6f2180ef0d42d5bb4c5cc7e52e06b18725c48760` |

Both restored processes loaded executables byte-identical to the original
Ubuntu DEB. Each grant was revoked and deleted. The sandbox then received
ENOENT. At the end all three synthetic backing files matched their original
device, inode, length and SHA-256. The final dpkg state was
`install ok installed 1.18.4-1ubuntu2.24.04.3`. The lease result has SHA-256
`be67c26b916f9dc0756e5458305f36ec4673d7be189d53d19678ce0400b6d02f` and
the VM receipt `71e32ce3a688b1364699e72d40b26c2106efc7e84f724e199b0f9e05d367655d`.
The fresh package VM `package-ay2dj2as` exited successfully. Its complete
source packages and all five binaries matched the original build. It ran
all 29 Meson suites. The upstream suite skipped three subcases concerning
an inhibit monitor, a headless directory handler and a trash directory.
All five Documents interface subcases passed. Its package and VM receipt
SHA-256 values are `6cd3c14cb7250845f01eef33e64903fc08e8d670606c0e4880910e9724c8abee`
and `cf7f0f89622ee58057e4a9806950d56fc62b2fd4a54bef54d7f8b78d7bfe81ed`.
Independent readback extracted both original DEBs from the verified input
ISO and compared the six running service images with the appropriate
archive members. It checked the installed Flatpak reader and runtime
commit and reread the final dpkg database, original service binaries and
all three media inodes and contents from the powered-off guest. Its
`lease-chain-review-26ktytm2/review.json` SHA-256 is
`7fe26b97c26cc4a08f7979509692d4685b4047bc1bb7a8f839970a9d90554a83`.
This establishes native x64 package feasibility. Distribution approval
remains open.

### Private service comparisons

At `a66e045` each Ubuntu runner recorded 28 checks against the packaged
daemon, 28 against its pristine rebuild and 42 against the private backport.
The packaged and pristine daemons returned errno 38 for the required
lease. Only the backport enforced contention across the portal and backing
views. All grants were revoked. The x64 case was `amd64-hmi8ytft` and
the ARM64 case was `arm64-f72e6u80`. The six observation/input hashes per
target matched their archived files. [Verified native archives](rw02-native-gui.md#native-follow-up-at-a66e045).

Each private service returned a fresh opaque document ID and a kernel mount of type `fuse.portal`. The exporter used the D-Bus `AddFull` method with a descriptor for a temporary directory and read/write authorization for `org.example.IfwServices`. A second mount namespace hid the entire producer directory from each grant consumer and dropped its capabilities. Both views contained the same regular synthetic JPEG fixture. The C# probe called `SecureWatchRoot.OpenRead`; the Rust probe called the workspace's `Directory::open_file`, checked the contents and revalidated the entry identity while keeping the handle open. A third, independent process requested nonblocking shared or exclusive `flock` leases on the same file. [Managed caller](../../tools/rust-qa/linux-services/dotnet/Program.cs) · [Rust caller](../../tools/rust-qa/portal-noble/read.rs) · [D-Bus and lock observations](../../tools/rust-qa/portal-noble/observe.py).

| Independent check | Packaged Noble service and unmodified source build | Private Ubuntu backport |
| --- | --- | --- |
| Uncontended read via grant | Both readers reported errno 38 | Both read the expected bytes |
| Shared reader and a second shared reader | Backing control succeeded. Grant requests reported errno 38 | Both directions acquired shared locks |
| Exclusive writer against a live shared lease | Backing control reported errno 11. Grant requests reported errno 38 | Both directions refused the writer with errno 11 |
| Exclusive lease held while Rust or C# requests a read | Backing contention observed. Grant requests reported errno 38 | Both directions refused the read. C# reported errno 11 and Rust reported `WouldBlock` |
| Release and subsequent acquisition | Backing access resumed. Grant still reported errno 38 | Both views allowed subsequent reads and exclusive acquisition |
| Revoke grant and read back the producer file | App view disappeared and contents were intact | App view disappeared and contents were intact |

The probe observes ordinary BSD `flock` operations on cooperating opens. An exclusive participant acquires its real lock on a read/write descriptor and checks the known bytes. The fixture's synthetic application identity is supplied by the private exporter. Installed Flatpak identity and desktop chooser behavior have their own tests. [Installed Flatpak grants](rw02-portal-dialog.md).

The offline run `amd64-kgndqoro` took 31.3 seconds on 2026-11-21. Its worktree was based on `c9b50ef371c724d5a2eb5c211cc46e20f5b9dfe9`; the report independently binds every fixture source file by SHA-256. .NET reported runtime 10.0.12. The top-level result SHA-256 is `73623ad642b3e10e429f72b13e2d64f4f96f0a685d75f7158ced7ee6f1055ad6`. Three fresh builds produced identical unmodified and patched executables.

| Running service SHA-256 | Document ID | Lease observations | Observation JSON SHA-256 |
| --- | --- | ---: | --- |
| Packaged `44dd7e1eb2df2a4de1d8c1189a3fee4451539ffab5db6ba4d21718c6d43af3dc` | `598dc14c` | 28 | `ae56165903f9735628a9e5ed4ed710c15f62823056beab77c673a19cf7ddc5ed` |
| Unmodified `d9c1db7cc7e00b592802a8a26ee273f062db5128845fcea51cf621acf41ce736` | `56d7c438` | 28 | `d3451b56ba68b0e3857ded0363fdabe884e020846022f5601292c90ff58efbe7` |
| Backport `17980d7a8269396cf9a711f01e05ea2d62eddc0cb9459a0380a639eb74512852` | `e42a75c2` | 42 | `503cfb9ccd034937eff0ea27de7fe328de83e7949f18c3b78a12784b92b272f3` |

## Development reader outcomes and retained-grant retry

The earlier Rust caller preserved errno 38 but emitted only `REFUSED errno=38`.
The development caller now reports an explicit outcome and next action for
failures of the normal `Directory::open_file` read-lease acquisition. It preserves
the native errno or Rust's normalized `WouldBlock` value. Root setup, content and
identity-validation failures remain fatal errors outside this classification.

| Read-lease failure | Outcome | Action |
| --- | --- | --- |
| `ENOSYS` (38), `EOPNOTSUPP` (95) | `UnsupportedFileLock` | `CheckPortalFileLockSupport` |
| `EAGAIN` (11), normalized `WouldBlock` | `FileBusy` | `RetryAfterWriterRelease` |
| `EPERM` (1), `EACCES` (13), normalized `PermissionDenied` | `AccessDenied` | `RestoreAuthorizedAccess` |
| Other errors | `ReadLeaseUnavailable` | `InspectNativeError` |

These are development-protocol observations for the fixed synthetic file, not a
production UI or a new core error API. Four Rust controls exercise unsupported,
busy, denied and unknown errors; three Python controls reject contradictory
outcomes/actions and unauthenticated package selections. Native errno 38 and
`WouldBlock` were observed below. The errno 95 and access-denied classifications
have pure controls, not additional native fault injections.

The `retry` mode opens the authorized root and album once and accepts exactly
three explicit attempts followed by `stop`. Each attempt uses the unchanged
filesystem adapter and its required shared lock. A failed acquisition returns
no file lease. Successful reads check the expected bytes and current entry
identity while the file lease is held. The retry releases a successful file
lease before reporting completion, retaining both directory handles throughout.
The observer independently reads the known Rust child's executable hash and
`/proc/<pid>/fd` records. It requires unchanged directory descriptor numbers,
device/inode identities and read-only `O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`
flags; the grant, backing-file identity and contents must also remain unchanged.
These metadata observations validate the fixture and confer no filesystem
authority on the consumer.

The observer binds the retry reader to its private input and output pipes and
holds its procfs process directory. `retryObservation` in `observation.json`
records the original grant and album descriptors before each attempt and on
failure. Each sample contains the descriptor number, file type, device, inode,
open flags and mount ID when the kernel provides one. Link labels identify the
two authorized directories, their deleted forms or an unrecognized target.
Before sending each attempt, the observer saves the sample and requires both
original numbered slots to match their directory identity, link and open flags.
Separate records retain the last verified stage, the failing stage and any
native metadata errors. Before deletion the observer records the explicit
revocation call, the grant's disappearance and the backing-file read separately.
A cleanup failure retains the primary observation error and fails the trial.

The offline native x64 run `amd64-msdhalx2` passed on November 22, 2026 in 42.238
seconds under Noble userspace and Fedora kernel `7.3.4-300.fc45.x86_64`. Its
worktree base was `8b64330ce64485597b37f0c37657b759ff21abd9`; the receipt binds all
fixture files and the actual workspace filesystem sources separately. The result
SHA-256 is `7a830f8e58e8ff3491521ae05701bf7d145ef8169e20a5c7e650b827d9abb7ac`.
The Rust reader SHA-256 is
`eb084203c16cb93ca4b9824e2286edd4953e7e33f85412b028ef115ac3c80c54`.
All source, executable, input and observation bindings were rechecked. The
existing three daemon hashes above were unchanged; no new backport was made.

| Service | Document ID | Lease observations | Observation JSON SHA-256 |
| --- | --- | ---: | --- |
| Packaged Noble | `8f7a4bea` | 32 | `a01dbe5ca24b21d775a590fe88cf8383fad5ec9715b07b3583d2e1e49dcfe0d0` |
| Unmodified rebuild | `900dae4d` | 32 | `2affa8a01dac9fe33db41ce3b4862d7d664e13d8322e7152272ab8a1c760fef1` |
| Existing private backport | `7433908b` | 46 | `5709fa41b3903284e13960dc819df94dcf656bf95a5098ced2eb38531d6fff1a` |

The stock and unmodified services reported `UnsupportedFileLock` with errno 38
on all three attempts, including before, during and after the independent
exclusive backing lease. The backport reported an acquired read, then
`FileBusy` while that exclusive lease was held, then an acquired read with the
same file identity after release. Both held directory descriptors remained
unchanged. All three grants were revoked after the checks. The synthetic bytes
retained SHA-256 `b52af4136a0ecafce322a09cbb3efeb16704396715fb7458e07382e7d6d8ef55`.

This demonstrates recovery from contention through the same retained grant on
the supported private service. The stock unsupported capability did not recover.
No retry across grant revocation, service replacement or backing identity change
was attempted. A supported released host fix and production error/retry UI
remain open. These added controls have run locally on x64; the earlier hosted
x64/ARM64 counts above describe the earlier fixture. The initial local attempt
`amd64-xxt06xb_` stopped after 28 observations because its observer incorrectly
expected `O_PATH` directory handles. The corrected observer checks the actual
read-only directory flags and passed in the fresh run recorded here.

### Incomplete ARM64 retry at `653f255`

Ubuntu ARM64 completed 32 operations with the packaged service and 32 with
the pristine rebuild. Both returned errno 38 and revoked the grant. With
the private backport, the Rust reader acquired file identity
`(58, 9330425294979592092)`, reported `FileBusy` while the writer held its
lease and acquired the same identity after release. After operation 46 the
observer could no longer identify both original directory handles by name.
That version saved neither the original descriptor numbers nor the final
revocation result on this error path. The reason for the missing names
remains unknown. The same ARM64 Rust reader and observer completed the
comparison in eight earlier archived runs, most recently at `1b95ba0`.
[ARM64 run and archived observations](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595514) · [Earlier native run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45210426209).

The ARM64 archive ID is `14848615669`, SHA-256
`2212804cf475e4867013fcc2f909728ddf34d3e997ae28ee40fa8f07ef89fb68`.
The partial backport observation hashes to
`c4b114f8440d14fcb7cbe6b7ed6835d8ae16961a46a2dd80d87af132607555bd`.
Locally, the unmodified observer at `873ad3f` completed 32, 32 and 46
operations on Fedora x64 with Noble userspace and verified all three
revocations. Its offline result at `amd64-dfx16b7p/result.json` hashes to
`fb4df7254a71c5a5a7b853dc3dc7b6dfbd1cb00edb1b080d678ecb1e15c2183a`.

Ubuntu x64 at the same hosted commit completed all 110 observations and
all three revocations. Its `amd64-tbpus43w/result.json` hashes to
`ffebe0015aa7a4ac6e72337ac796d730a223f09a4a9b230b289bcbc2449d49a0`.
[x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595514/artifacts/14848454057).

### Name and permission observations during a refused retry

In the local Noble x64 run `amd64-ign09cwt`, the packaged service reached
30 operations. Before the second retry the kernel labelled the original
FDs 3 and 4 as the known grant and album paths with ` (deleted)` appended.
Both remained directories with their original device, inode, mount and
open flags. The observer stopped the request. Its original record hashes
to `20a7f0ab580b249762a5e24efb466227a148ced0ca2f6777fb6af7a7c283f34c`.

A second offline run, `amd64-bu6v8flq`, measured the names and permissions
before releasing the synthetic writer or revoking each grant. The packaged,
pristine and patched services reached 30, 30 and 44 operations respectively.
All three recorded both detached names. A fresh lookup through the named
grant returned the same device and inode for each directory. The private
exporter's `Documents.Info` call for the original document ID reported the
synthetic source and the test application's read and write permissions.
A later sample of both original FDs again showed the original names. In
each case the observer kept the failed result, verified grant revocation
and read back the original synthetic bytes. The result SHA-256 is
`3dc6eefa7d196dcda7d72113f74ad543a8739eae7786fe69e4b915d02a93124e`.
Noble's implementation schedules cache invalidation after a successful
lookup of a physical entry. The precise kernel event in the failed ARM64
run remains unknown. [Ubuntu source inputs](../../tools/rust-qa/portal-noble/inputs.py).

### Checking the reader while both named directories are open

The observer takes a raw sample of the two original Rust descriptor slots.
It verifies their numbers, directory types, devices, inodes and open flags.
It also compares the original kernel mount ID when present. If the kernel
reports exactly the original name followed by ` (deleted)`, the private
exporter must confirm the original token, synthetic backing path and
the test app's read and write permissions. Any other changed link fails.

For the same observation, the observer holds the named grant open and
opens the album relative to that directory descriptor. Both opens require
`O_DIRECTORY | O_NOFOLLOW`. While the two observation handles are live,
the reader's original numbered slots must once again have the exact
canonical names and all their original properties. Both named directory
identities and the unique matching descriptors must agree. The observer
performs this comparison once before each attempt and at the end. Only
the Rust reader's original handles are used for the synthetic reads.

The first implementation ran offline in `amd64-p5elg3re` on the working
tree based on `6bfcdbc`. All three services displayed the detached
labels before attempts two and three. Six independent grant lookups
returned the expected origin and permissions. All 24 final slot samples
across the twelve observations matched the original directories. The
stock services returned errno 38 and the backport recovered after the
writer released its lock. All three revocations and final content checks
passed. Its native result SHA-256 is
`75d508ea97533bff6d807db5b4f7a7569883407ed5f66a218213834480e0bc99`.

At the clean revision `dc339e48517eeb28fbd7b7f8a536cccf61c0a70c`,
`amd64-e03cc583` repeated all three comparisons offline in 30.99 seconds.
The two stock services each completed 32 observations, including the three
errno 38 refusals. The backport completed 46, including the busy reader
and acquisition of the original file after writer release. The twelve
directory comparisons bound all 24 confirmed Rust descriptor slots to
the original mount IDs. Every service recorded two independent lookups
for detached names and one verified revocation. The result hashes to
`d1e56368fb2bfb15e1fada54838fe836996d31c07376c13edf03e11db7de329b`.
The detached readback verified the eleven fixture files and five Rust
filesystem sources against Git and the locally rebuilt binaries against
the receipts. Its SHA-256 is
`bcf4ae99aa66bb965af3e821072a20238339976a197c005b805107602fe775e7`.

### Native Ubuntu repeats with the earlier observer at 1904be7

Both native Ubuntu runners completed 32, 32 and 46 operations with the
package, unmodified rebuild and private backport respectively. The first two returned
`ENOSYS` for all 17 requests to lock the granted file. With the backport,
13 grant operations acquired the lock and 11 reported a busy file. The
reader reacquired the original file after the exclusive writer released
it on each architecture. The three daemon logs from each host showed the
test application's permissions being revoked and the backing contents survived. Independent readback
matched the root and album descriptor slots 3 and 4 at both endpoints.
This revision predates the intermediate permission and mount-ID samples.

| Original archive | Private run | Portal result SHA-256 |
| --- | --- | --- |
| [Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230321156/artifacts/14856775741) | `amd64-yzfn66wj` | `07e387feed94108cf0f4a0714648577ece315abf7469a837807a25a0f0f95235` |
| [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230321156/artifacts/14854477018) | `arm64-i_4c226j` | `398a0ddc2a96ef754188685be9ac03afb5ee316d20011d040473f0191b3a12c9` |

### Native descriptor replay at 6084b23

On Ubuntu ARM64 the corrected observer completed all 110 operations and
revoked the three independent grants. Detached replay matched eleven
fixture and five filesystem sources with Git, all 24 original descriptor
slots and their mount IDs, and six lookups while the original names carried
the kernel's detached label. The distro and its pristine rebuild returned
errno 38 on all seventeen grant attempts each. With the backport, the Rust
reader acquired the same original file after the writer released its lock.
The `arm64-k2icsihg` result SHA-256 is
`0dc0dcdbd9f60e8e06e139f2eee9686ac556c1e573f71f4606cfd690eaa6c191`.
[Original native ARM64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45242083236/artifacts/14861975652).

On x64 the Ubuntu package completed 31 operations. Before the third Rust
read the observer saw the exact grant and album names on descriptors 3
and 4. While it held both independently opened named directories, the
kernel added ` (deleted)` to the grant's descriptor label. The album
retained its name. Both descriptors kept their original device, inode,
flags and mount ID 504. The observer stopped before sending the third
request. The original document still granted read and write permission
to the test application. Its subsequent revocation and deletion succeeded.

The unmodified rebuild completed all 32 operations and returned errno 38
for all seventeen grant lock attempts. The private backport completed all
46 operations, including contention and reacquisition of the same file.
All three original files survived revocation with the expected contents.
The `amd64-w9i6r7vr` result SHA-256 is
`7f7be799c7cf3163fc2634ff17d0350715a706fe7fd64d143318da30a5af59dd`.
[Original native x64 archive](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45242083236/artifacts/14863376245).

### Walking the album through the reader's original grant

Noble's Documents implementation queues invalidation of a physical
directory entry after a successful lookup. An open descriptor can retain
the same directory while procfs displays its former name with
` (deleted)` appended. The x64 trace above shows the label changing
between two observations. Linux resolves an open through a numeric procfs
descriptor using the file's held mount and directory entry.
[Ubuntu source package and patch inputs](../../tools/rust-qa/portal-noble/inputs.py)
· [Linux procfs descriptor lookup](https://github.com/torvalds/linux/blob/v7.0/fs/proc/fd.c#L165-L184).

The observer first opens the named grant and its relative album in the
waiting Rust process's mount namespace. It matches each to one unique
reader descriptor by role, directory type, device, inode, mount ID and
the full set of flags on the independent read-only open. It rechecks
both numbered slots. Before each read and after the
last read it opens the named grant in that process's mount namespace and
opens `album` relative to it with `O_NOFOLLOW`. It compares the directory
types, devices, inode numbers and mount IDs to the reader's original
descriptors. It checks descriptor numbers, flags and names again in the
original slots and the process's descriptor list.

If an original slot shows its exact former name and the kernel suffix,
the observer looks up the original document ID and verifies the backing
directory and both permissions of the test app. It then opens the
reader's original grant through the bound numeric procfs descriptor and
walks to `album` from there. Both directories must match the independently
opened named pair including their mount IDs. The receipt retains the
observed labels, permissions and both walks. A mismatched or ambiguous
descriptor, denied grant or different child stops the request. The actual
Rust read still runs through the two handles it opened at startup.
[Observer](../../tools/rust-qa/portal-noble/observe.py)
· [Regression checks](../../tools/rust-qa/portal-noble/test_descriptors.py).

In the first native test of the relative walk, the x64 Noble userspace
on the Fedora kernel completed 32, 32 and 46 operations with the three
services. Six detached-name observations confirmed the document rights
and both directory identities through the reader's root. The result
SHA-256 for `amd64-71qu46tv` is
`8b19cc9df0412e2a862c0deb89318e009fcb32def8b902cd2c5eb5a219ba164f`.
At `ce62051` the stock service exposed a detached album label during the
initial binding. The earlier observer stopped there after 28 operations.
The unmodified rebuild and backport passed, and all three grants were
revoked. The `amd64-e_4ucz7a` result SHA-256 is
`3900ccdbfd15cf3a2f81b019bad4902bd94e3289050eb92d2cd03f434915941e`.
The revised initial binding applies the permission and original-parent
checks to a detached name at this first observation as well.

## Meson on the Ubuntu runners

Both Ubuntu architectures in workflow run `44950398558` authenticated the Documents package and stopped at the first Meson invocation. The x64 build added 32 signed development packages and ARM64 added 31. Both installed Meson `1.3.2-1ubuntu1` into the private development layer and used the runner's existing Python. Their error logs have the same SHA-256, `9b2f75b0451e1d2ae46a0fb887ef10734a2343943284bd5a6f22f86e59405a17`. Neither job reached the lock measurements. [Hosted assessment](https://github.com/voltkraft/immich-folder-watch/actions/runs/44950398558).

The local x64 control selected the same distribution Python executable from the read-only Noble runtime and kept Meson in the development layer. Python followed the interpreter symlink and chose `/noble-usr` as its prefix. The package was visible under the merged `/usr`, but Python searched only the runtime layer. Executing the real Meson launcher reproduced the hosted traceback byte for byte. The build now supplies `PYTHONHOME=/usr`, gives the distribution package directory priority, and disables the user site. Before configuration it starts the real launcher, checks its version against the imported package, and records the resolved interpreter, launcher, module paths and file hashes. [Python module search path initialization](https://docs.python.org/3.12/library/sys_path_init.html) · [Meson check](../../tools/rust-qa/portal-noble/meson_python.py).

Two offline runs under the local Noble x64 userspace on November 21, 2026 confirmed the correction. Both compiled the same pair of daemon binaries as the earlier control. Each performed 28 lock checks with the packaged service, 28 with the source control and 42 with the private backport, then revoked all three grants. Both hosted architectures subsequently completed these steps on November 22.

| Private compiler layout | Run under `artifacts/rust/portal-noble/runs/` | Result SHA-256 |
| --- | --- | --- |
| Runtime Python and development-layer Meson | `amd64-vlxw1ad1` | `549b17d44ea12e91c8280f9f08365e0088189c19b3d57be314eb1b84f218157f` |
| Python and Meson in the same development layer | `amd64-cx1dy5mt` | `15901a02c80ce65585d59d24142a3c786b91420bd4d987a6b659958246766d82` |

## Source, package and license binding

The public source comes from Ubuntu's signed `noble-updates/main/source/Sources.xz`. The recipe verifies Ubuntu Archive Automatic Signing Key (2018) fingerprint `F6ECB3762474EDA9D21B7022871920D1991BC93C`, the index digest, the exact package version and all four source objects. It independently checks the binary package SHA-256 and verifies the installed daemon, permission store and copyright file against that package. Both running service executables are then hashed through their private `/proc/<pid>/exe` descriptors. Each native run records its input and output hashes. [Archive validation](../../tools/rust-qa/portal-noble/verify.py) · [Source archive pins](../../tools/rust-qa/portal-noble/inputs.py).

`dpkg-source` applies all ten Noble packaging patches first. Both builds use the same Meson options, compiler and build-only declarations `-D_GNU_SOURCE=1 -include sys/file.h`. Ubuntu's package carries libglnx as a separate original archive and links it into `subprojects/libglnx` as specified in `debian/rules`. No subproject download is permitted. Only the Documents daemon is built. The patched function is byte-identical to the function in upstream commit `caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57`. The resulting complete C file changes from SHA-256 `aff36d56cc496e449047ad17d024139812b7160ef6d8f1e5b3eb22fbb5b76730` to `a3cf626fa1e2971b9e3a7bfb0081c353c79603a75a30c5a2b8db82a36b432f92`. The build inventories every source-file change and verifies the original notices and FUSE headers. [Build recipe](../../tools/rust-qa/portal-noble/build.py) · [Noble-specific patch](../../tools/rust-qa/portal-noble/flock.patch).

The patch is a development adaptation of Sebastian Wick's upstream change. The original Documents source credits Red Hat, Inc. and GNOME Foundation Inc. and uses LGPL-2.1-or-later. The Noble GVDB sources use LGPL-2.0-or-later. Bundled libglnx contains LGPL-2.0-or-later and LGPL-2.1-or-later files. Ubuntu's FUSE 3.14.0 headers and library carry the upstream LGPL-2.1 terms. The recipe retains the original source and Ubuntu packaging notices, hashes the exact FUSE inputs, and records package versions, development copyright files and the 15 loader-resolved libraries in the local comparison. The Ubuntu loader and all host services remain system-supplied. The three daemons are development subjects. This work adds no portal binary or library to application distribution. [Retained upstream license](../../tools/rust-qa/portal-reference/LICENSE.upstream-LGPL-2.1.txt) · [libfuse 3.14.0 licensing](https://github.com/libfuse/libfuse/blob/fuse-3.14.0/LICENSE).

## Reproduction

The dated Ubuntu snapshot at `20261121T210000Z` supplies the four pinned
source files and their signed Noble Updates index. The checked index is
`b429a53b7e513a73ef21d49ae88e619434efc8fc2789b9b389a2eaeca3c7d42f`.
The helper verifies Ubuntu's release signature, source record, sizes and
file hashes. For development and control binaries it uses the date from
the authenticated runner index that supplied each package hash. Locally
the frozen release, all four source files, 147 selected development package
records and the original native control package verified. An HTTP refusal
retains the specific public URL in the error report. [Ubuntu Snapshot Service](https://snapshot.ubuntu.com/) · [Acquisition and verification](../../tools/rust-qa/portal-noble/verify.py).

On a disposable Ubuntu Noble x64 or ARM64 runner, first build the existing `linux-services/native.py oracle` and install the project's pinned Rust toolchain. The runtime needs the packaged Documents portal, its permission store, Python GI, Bubblewrap, a usable private user namespace and `/dev/fuse`. The build consumes the runner's existing authenticated Noble APT lists. Missing Meson, Ninja, compiler tools and development headers are resolved against signed Ubuntu package indices and extracted into a private compiler view. No APT installation, maintainer script or host service restart is performed.

```sh
export IFW_QA_REFERENCE_SDK="${DOTNET_ROOT:?}"
python3 -B tools/rust-qa/portal-noble/run.py --hosted --download
```

For the maintained local private Noble x64 userspace, run `python3 -B tools/rust-qa/portal-noble/run.py --local-noble --download`. Once the signed source metadata, source archives and required development packages are in the private cache, omitting `--download` runs the comparison offline. Run the following controls from the repository root on Linux. The hosted Ubuntu jobs run them before the native comparison.

```sh
python3 -B -m unittest discover -s tools/rust-qa/portal-noble -p 'test_*.py'
```

The controls cover signed package selection, native error classification,
descriptor identity before every retry and separate records for read and
revocation failures. The native build also compiles and executes the four
Rust classification controls, retaining `build/reader-tests.log` and its digest.

Use `python3 -B tools/rust-qa/portal-noble/run.py --local-noble --local-split-python` to exercise the hosted package layout offline with the local Noble userspace. The fixture verifies the two interpreter binaries are byte-identical and selects the runtime copy through a link in the newly created private compiler view. It retains the original Meson error in `build/split-python-control.log`. Every build collects the corrected interpreter and Meson inputs in `build/meson-python.log` and the final result.

Every run creates a new `artifacts/rust/portal-noble/runs/<arch>-<id>/`. Preserve `result.json`, each of `packaged/`, `unmodified/` and `backport/` with its JSON/log files, `development/apt-packages.json`, `development/build-packages.json`, `development/package-notices.json` and `build/*.log`. Generated build trees, package archives and executables stay private. [Native launcher](../../tools/rust-qa/portal-noble/run.py).
