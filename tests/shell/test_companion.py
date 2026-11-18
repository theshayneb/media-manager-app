import json
from pathlib import Path

import pytest

from media_manager import companion
from media_manager.settings import MediaSettings
from photo_manager.core.settings import Settings as PhotoSettings

INTEROP = Path(__file__).resolve().parents[2] / "android" / "core" / "build" / "interop.jpg"


def test_companion_file_for_the_android_app(tmp_path):
    photos, media = PhotoSettings(), MediaSettings()
    photos.keyword_sets = {"Shayne": ["me", "josh"], "Trips": ["paris"]}
    media.last_edit = {"brightness": 20}
    old = tmp_path / "Media Manager" / "companion.json"  # where 0.6.0 put it
    old.parent.mkdir()
    old.write_text("{}", encoding="utf-8")
    path = companion.write(photos, media, tmp_path)
    assert path == tmp_path / "Documents" / "Phone" / "Media Manager" / "companion.json"
    assert not old.exists() and not old.parent.exists()  # moved
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["keyword_sets"] == {"Shayne": ["me", "josh"], "Trips": ["paris"]}
    assert data["rename_pattern"] == photos.rename_pattern and data["last_edit"] == {"brightness": 20}
    assert data["templates"][0]["pattern"].startswith("PXL_")
    before = path.stat().st_mtime_ns
    companion.write(photos, media, tmp_path)  # unchanged: not rewritten (no OneDrive upload)
    assert path.stat().st_mtime_ns == before


@pytest.mark.skipif(not INTEROP.exists(), reason="the Android core tests make it (gradle :core:test)")
def test_photo_tagged_by_the_android_app_reads_on_the_pc():
    from photo_manager.core.exiftool import ExifTool, find_exiftool
    from photo_manager.core.metadata import READ_TAGS, parse_meta

    if not find_exiftool():
        pytest.skip("needs ExifTool")
    with ExifTool(find_exiftool()) as et:
        [data] = et.read([str(INTEROP)], READ_TAGS)
    meta = parse_meta(data)
    assert meta.keywords == ["josh", "new york", "café"]
    assert meta.label == "Green" and meta.starred and meta.bookmarked and meta.edited
