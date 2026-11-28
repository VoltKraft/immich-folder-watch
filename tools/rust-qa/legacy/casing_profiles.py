"""Reproduce the two observed invariant-uppercase profiles from pinned Unicode data."""

import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
LICENSE = HERE / "licenses/Unicode-LICENSE.txt"
LICENSE_SHA256 = "e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96"


@dataclass(frozen=True)
class Profile:
    version: str
    source_sha256: str
    table_sha256: str
    changed_scalars: int

    @property
    def table(self) -> Path:
        return HERE / "casing" / f"unicode-{self.version}.tsv"


PROFILES = (
    Profile("15.1.0", "2fc713e6a31a87c4850a37fe2caffa4218180fadb5de86b43a143ddb4581fb86",
            "02c4363688e37251e1169559be56231d6e9c398ba046ea3773cdf037df72cd2f", 1449),
    Profile("17.0.0", "2e1efc1dcb59c575eedf5ccae60f95229f706ee6d031835247d843c11d96470c",
            "195bd89b3934dcf9c93b72b4232c53d9787dacb8ebbf2270df7a6a73e53f473e", 1504),
)


def simple_uppercase(source: bytes) -> dict[int, int]:
    pairs = {}
    for line in source.decode("utf-8").splitlines():
        fields = line.split(";")
        if len(fields) != 15:
            raise ValueError("Invalid UnicodeData record")
        if fields[12]:
            pairs[int(fields[0], 16)] = int(fields[12], 16)
    return pairs


def derive(profile: Profile, source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != profile.source_sha256:
        raise ValueError(f"Wrong UnicodeData.txt for {profile.version}")
    pairs = simple_uppercase(source)
    # .NET invariant uppercase preserves LATIN SMALL LETTER DOTLESS I.
    if pairs.pop(0x0131) != 0x0049 or len(pairs) != profile.changed_scalars:
        raise ValueError("Unexpected invariant uppercase exception or table size")
    rows = ["IFW-INVARIANT-UPPERCASE-V1\n"]
    rows.extend(f"{source:06X}\t{upper:06X}\n" for source, upper in sorted(pairs.items()))
    table = "".join(rows).encode("ascii")
    if hashlib.sha256(table).hexdigest() != profile.table_sha256:
        raise ValueError("Derived data differs from the qualified casing profile")
    return table


def require_notice() -> None:
    if hashlib.sha256(LICENSE.read_bytes()).hexdigest() != LICENSE_SHA256:
        raise ValueError("The original Unicode license notice differs")


def match_reference(reference: bytes) -> Profile | None:
    """Identify complete map bytes, independent of OS, architecture or .NET version."""
    require_notice()
    checksum = hashlib.sha256(reference).hexdigest()
    for profile in PROFILES:
        if checksum == profile.table_sha256:
            if reference != profile.table.read_bytes():
                raise ValueError("The checked-in Unicode table differs from its approved digest")
            return profile
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", choices=[profile.version for profile in PROFILES])
    parser.add_argument("unicode_data", type=Path, help="Official UnicodeData.txt for that version")
    parser.add_argument("--write", action="store_true", help="Regenerate the checked-in development fixture")
    args = parser.parse_args()
    require_notice()
    selected = next(profile for profile in PROFILES if profile.version == args.version)
    table = derive(selected, args.unicode_data.read_bytes())
    if args.write:
        selected.table.write_bytes(table)
    elif selected.table.read_bytes() != table:
        parser.exit(1, "Checked-in casing fixture differs from its original source\n")
    print(f"Unicode {selected.version}, {selected.changed_scalars} mappings, {selected.table_sha256}")
