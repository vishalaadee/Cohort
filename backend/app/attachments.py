"""Drive attachments: the limits, the allow-list, and filename handling.

Lives outside the routers because two of them need it. `placement.py` serves
the officer's download and `portal.py` serves the student's, and when each had
its own sanitiser they disagreed: the same file arrived as
`rubicon-sde1-jd-pdf` for the officer and `rubicon-sde1-jd.pdf` for the student.
"""
from __future__ import annotations

import posixpath
import re

MAX_ATTACHMENTS_PER_DRIVE = 3
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024

# An allow-list, not a block-list. A placement officer has no reason to attach
# anything executable to a drive, and "reject what we know is bad" is the rule
# that eventually lets through the thing nobody thought of.
ALLOWED_ATTACHMENT_MIMES = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
ATTACHMENT_KINDS = {"jd", "form", "brochure", "other"}

_STEM_OK = re.compile(r"[^A-Za-z0-9 ._-]+")
_RUNS = re.compile(r"[ _-]{2,}")


def safe_filename(filename: str | None, mime: str | None = None,
                  fallback: str = "attachment") -> str:
    """A filename safe to put in a Content-Disposition header.

    Not `_safe_slug`. That one replaces every non-alphanumeric — including the
    dot — so `rubicon-sde1-jd.pdf` comes out as `rubicon-sde1-jd-pdf` and the
    browser saves a file the operating system cannot open. It is correct for
    what it was written for (a company name, where the caller appends `.csv`)
    and wrong for a name that already carries its own extension.

    Rules:
      * take the basename, so a crafted `../../etc/passwd` cannot escape;
      * keep the extension, deriving it from the MIME type when the name has
        none or a name written in a non-Latin script leaves nothing behind;
      * never return a name that is empty, or only dots.
    """
    raw = (filename or "").strip()
    # Basename under both separators — a Windows client sends backslashes and
    # posixpath alone would keep the whole path as one segment.
    raw = posixpath.basename(raw.replace("\\", "/"))

    stem, dot, ext = raw.rpartition(".")
    if not dot:                       # no extension at all
        stem, ext = raw, ""

    stem = _STEM_OK.sub("", stem)
    stem = _RUNS.sub("-", stem).strip(" ._-")[:80]

    ext = _STEM_OK.sub("", ext).strip(" ._-").lower()[:10]

    # When we know the stored content type, its extension wins over whatever
    # the name claimed. Upload only accepts allow-listed types, but the NAME is
    # free text: someone can store `cmd.exe` with a PDF body, and without this
    # the browser would be told Content-Type: application/pdf and still save
    # `cmd.exe`. The extension a file is saved with should describe what is
    # actually inside it.
    if mime:
        known = ALLOWED_ATTACHMENT_MIMES.get(mime.split(";")[0].strip().lower())
        if known:
            ext = known.lstrip(".")

    if not stem:
        stem = fallback
    return f"{stem}.{ext}" if ext else stem
