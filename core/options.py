"""What the user asked for, per run. Each cleaning step and the compression
pass are independent switches: any combination is valid as long as at
least one is on."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Options:
    metadata: bool = True     # DocInfo/XMP in PDF, docProps in Office
    signatures: bool = True   # PDF digital signatures and DocMDP perms
    protection: bool = True   # Office edit protection (read-only, sheets...)
    passwords: bool = True    # decrypt for good + drop PDF permission flags
    compress: str | None = None  # profile name from processors.compress

    @property
    def cleans(self) -> bool:
        return self.metadata or self.signatures or self.protection or self.passwords

    @property
    def anything(self) -> bool:
        return self.cleans or self.compress is not None
