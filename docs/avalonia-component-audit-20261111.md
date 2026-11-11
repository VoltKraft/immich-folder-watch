# Avalonia shipped-component audit (2026-11-11)

## Scope and method

Independent read-only audit for PR #32, preserving AGPL-3.0-only. Inputs are the
four public v3.0.2 release assets, exact upstream package/source revisions and the
new reduced packages. Assets were size/SHA-256 verified, then statically extracted
into isolated scratch storage. No application installation/execution, personal
Flatpak remote change or live Immich connection occurred.

PE/CLI metadata parsing examines actual TypeDef rows, including nested/nonpublic
types, rather than treating arbitrary strings or references as implementations.
Compiled theme markers and source/resource inclusion are checked separately.
This is a bounded Avalonia component audit, not a claim that every dependency's
complete licensing has been independently re-audited.

## Existing release finding

Both v3.0.2 Linux architectures contain the following identical DLLs. Their bytes
match the official Avalonia 12.0.3 NuGet assemblies, and dependency manifests
identify that version.

| Assembly | Bytes | SHA-256 |
| --- | ---: | --- |
| Avalonia.Controls.dll | 1301504 | `9ce4a80e90f13056b803f01e284bb95dbd8cb7297ae55b1d4e941b5cc311916c` |
| Avalonia.Themes.Fluent.dll | 712704 | `51bbae40524c0917e7c071093c11c9156b0ba26b2b8bfbf9e24bd098469c5cc1` |

The shipped Controls assembly defines Calendar, AutoCompleteBox,
CalendarDatePicker, LayoutTransformControl and associated types. Fluent contains
corresponding compiled-code markers. Exact 12.0.3 source revision
`21e816874efa142bf9903b51fd323d1f35e56ab3` contains the MS-PL headers; this issue
predates the proposed 12.1.6 upgrade. Successful earlier CI/publication did not
resolve this distribution/license concern. It is not a demonstrated exploit.

Static inspection of each Windows x64/ARM64 MSI found 415 managed assemblies,
zero Avalonia namespace definitions and zero parser failures. Windows uses WPF.
Existing release artifacts remain immutable and are not repaired by this PR.

## Source reduction and retained attribution

Target upstream 12.1.6 commit:
`cf8e564674700348947e93ab19105f27afe859a9`.
Its source archive SHA-512 matches
`cc83f37e77cd343abae304656a64b59f75ce8fdc181486df66e61e018cd309a156a9332235bb15a6fa3a64866fb806137ed9c9806f216c21126bc96b6b6f11e8`.

The source scan finds 19 MS-PL Controls C# files, seven Fluent XAML files, eight
Simple XAML files, plus the Silverlight-derived LayoutTransformControl. Every
identified path is covered by the checked-in removal inventory. Default Controls
compilation and Fluent `**/*.xaml` inclusion explain why merely not using those
controls in application XAML is insufficient.

The application does not use removed controls, transforms, ProgressBar or
NotificationCard. Desktop notifications use the D-Bus portal. ComboBox and ToolTip
use modified popup templates; explicit light/dark GUI regressions verify those
paths. Transformed popup layout is not supported by this reduced variant.

Retained Avalonia.Base contains 17 SixLabors Apache-2.0 source headers and the
Apple 2016 BSD-2-Clause SpringSolver header not represented by upstream NOTICE
headings. Supplemental attribution includes the complete Apache-2.0 text from
`SixLabors/Fonts@034a440aece357341fcc6b02db58ffbe153e54ef` (SHA-256
`f38dc2765451fd2b19d7e0f47ed655f3a1cb889b28341ea6266efd75d8425a6f`) and complete
Apple header (SHA-256 `696f17436cd30cb4c02c0343cb58c91e685d1b67fae528bab6d84514e3c0c3bf`).
Source provenance and exact texts live in `packaging/flatpak/licenses`.

## Independently inspected private packages

| Package | SHA-256 |
| --- | --- |
| avalonia.12.1.6.1.nupkg | `63c006b1a9a145db974f50abbbfa90945f6fae7b8882ce7f4ec8bf63cbb8d09a` |
| avalonia.themes.fluent.12.1.6.1.nupkg | `86209baf189616c4e1d2cb30334cd3fb48392bd4cf5290c4ed8c8dd139c02471` |

All 30 managed DLLs in these packages pass excluded-type inspection, including
nested names. Fluent contains no Calendar/AutoComplete/LayoutTransform markers.
Only intended package metadata/provenance and Controls/Fluent replacements differ;
unsupported net8 copies and invalidated upstream package signatures are removed.
Retained official net10 DLLs are byte-identical. Added upstream LICENSE/NOTICE
texts exactly match the pinned source; removal provenance matches the recipe.

Rebuilt Controls SHA-256:
`dd06f5e9243d3a95f45c0985a1f92c96d517e7bc746ea6d768c06125f8c08d04`.
Rebuilt Fluent SHA-256:
`8f762376626068c2da4db11a9ece2775cd510e23c9705be7790dc28e4196c654`.

Independent review additionally reproduced a verifier weakness where edited
extracted-cache provenance could authorize another DLL without changing the
archive. The verifier now derives provenance and DLL bytes directly from the
trusted rebuilt ZIP and rejects modified cache metadata. The original tampering
reproduction is rejected after the fix, with a dedicated regression test.

Three independent build directories, including one outside Git, produced identical
package bytes. Actual restored archive verification passes. Negative controls
replacing either rebuilt DLL with the official original are rejected; directly
auditing the original upstream package also fails as intended.

## Integration acceptance

The Linux test suite passes 60 cases, including protocol integration, five
loaded-assembly exclusion checks and actual dropdown/tooltip opening in both
themes. Full application publish provenance and installed supplemental notices pass.
Both architecture feeds are regenerated and all 95 official archive hashes
verified. Current-head hosted CI/CodeQL and final native candidate artifacts
remain pending at this checkpoint. [Framework maintenance contract](reduced-avalonia.md).
