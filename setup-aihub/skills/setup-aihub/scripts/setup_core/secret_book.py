"""Read the selected dependency's public metadata before delegating a write."""
from pathlib import Path
import re
import tomllib

from .errors import SetupError

TESTED_RELEASE = "2.5.1"
TESTED_COMMIT = "ee9c7ec0899ab63174b2b28010fa279376c2fa47"
STABLE_VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


def _identity_scalar(raw):
    # Read only the published artifact's simple name/version scalars. Unsupported
    # YAML forms fail closed instead of guessing a dependency's identity.
    match = re.fullmatch(r'''\s*(?:"([^"\\]*)"|'([^']*)'|([A-Za-z0-9][A-Za-z0-9._-]*))[ \t]*(?:\#.*)?''', raw)
    if not match:
        raise ValueError("unsupported identity scalar")
    return next(value for value in match.groups() if value is not None)


def _skill_identity(frontmatter):
    blocks = {}
    current = None
    for line in frontmatter.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0].isspace():
            if current is None:
                raise ValueError("invalid frontmatter indentation")
            blocks[current][1].append(line)
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):([^\r\n]*)", line)
        if not match or match[1] in blocks:
            raise ValueError("invalid or duplicate frontmatter field")
        current = match[1]
        blocks[current] = (match[2], [])

    def scalar(key):
        value, children = blocks[key]
        if children:
            raise ValueError("identity must be a scalar")
        return _identity_scalar(value)

    name = scalar("name")
    versions = [scalar("version")] if "version" in blocks else []
    if "metadata" in blocks:
        value, children = blocks["metadata"]
        if value.strip() and not value.lstrip().startswith("#"):
            raise ValueError("metadata must be a block mapping")
        fields = {}
        for line in children:
            match = re.fullmatch(r"  ([A-Za-z_][A-Za-z0-9_-]*):([^\r\n]*)", line)
            if not match or match[1] in fields:
                raise ValueError("invalid or duplicate metadata field")
            fields[match[1]] = match[2]
        if "version" in fields:
            versions.append(_identity_scalar(fields["version"]))
    if not versions or any(not STABLE_VERSION.fullmatch(value) for value in versions):
        raise ValueError("stable skill version required")
    if len(set(versions)) != 1:
        raise ValueError("conflicting skill versions")
    return name, versions[0]


def compatibility(caller):
    # Test evidence is separate from the selected installation's identity.
    return {"minimum_verified_release": "2.5.0" if caller else "2.5.1",
            "tested_release": TESTED_RELEASE, "tested_commit": TESTED_COMMIT,
            "verification": "native_windows_public_cli_synthetic_lark",
            "caller_mode": "skill" if caller else "plugin_shared",
            "live_table": "not_verified"}


def inspect_dependency(root, caller):
    evidence = compatibility(caller)
    options = ["核对或安装兼容的 Secret Book", "自行填写本机文件", "暂不配置"]
    if not root:
        raise SetupError("secret_book_location_required", compatibility=evidence, options=options)
    try:
        path = Path(root).resolve(strict=True)
        for name in ("scripts/secret_book.py", "references/roles.md", "references/consumer-setup.md",
                     ".python-version", "uv.lock"):
            if not (path / name).is_file():
                raise ValueError("incomplete artifact")
        metadata = []
        for name in ("pyproject.toml", "SKILL.md"):
            with (path / name).open("rb") as stream:
                raw = stream.read(256 * 1024 + 1)
            if len(raw) > 256 * 1024:
                raise ValueError("metadata too large")
            metadata.append(raw.decode("utf-8-sig"))
        project = tomllib.loads(metadata[0])["project"]
        frontmatter = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", metadata[1], re.S)
        if not frontmatter or project.get("name") != "secret-book":
            raise ValueError("wrong artifact")
        version = project["version"]
        if not isinstance(version, str) or not STABLE_VERSION.fullmatch(version):
            raise ValueError("stable version required")
        if _skill_identity(frontmatter[1]) != ("secret-book", version):
            raise ValueError("inconsistent metadata")
    except (OSError, ValueError, KeyError, TypeError):
        # Never echo source text or parser errors from an arbitrary local file.
        raise SetupError("secret_book_artifact_invalid", compatibility=evidence, options=options) from None
    dependency = {"root": str(path), "version": version, "evidence": "public_metadata_only"}
    if tuple(map(int, version.split("."))) < tuple(map(int, evidence["minimum_verified_release"].split("."))):
        raise SetupError("secret_book_version_incompatible", dependency=dependency,
                         compatibility=evidence, options=options)
    return dependency
