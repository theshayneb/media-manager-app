import array
import os
import shutil
import subprocess

import pytest

from media_manager import trim

FFMPEG = shutil.which("ffmpeg") or next((str(p) for p in __import__("pathlib").Path("vendor/ffmpeg").rglob("ffmpeg*")
                                         if p.is_file()), None)
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")


def _make(path, seconds=10, extra=()):
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-ac", "2", "-c:a", "libmp3lame", "-q:a", "0", *extra,
                    "-metadata", "title=Song", "-metadata", "artist=Someone", "-id3v2_version", "3", str(path)],
                   check=True)


def _decode(path):
    proc = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                          capture_output=True, check=True)
    assert proc.stderr == b"", proc.stderr  # decodes without complaints
    a = array.array("h")
    a.frombytes(proc.stdout)
    return a


def _rms(samples):
    return (sum(s * s for s in samples) / max(1, len(samples))) ** 0.5


@needs_ffmpeg
def test_cut_keeps_tags_and_length(tmp_path):
    src = tmp_path / "a.mp3"
    _make(src)
    data = src.read_bytes()
    assert abs(trim.mp3_duration(data) - 10) < 0.1
    dst = tmp_path / "b.mp3"
    trim.trim_file(FFMPEG, str(src), str(dst), 2.0, 8.0)
    from mutagen.mp3 import MP3

    m = MP3(dst)
    assert str(m["TIT2"]) == "Song" and str(m["TPE1"]) == "Someone"
    assert abs(m.info.length - 6.0) < 0.1  # the Xing header has the new length
    assert abs(len(_decode(dst)) / 8000 - 6.0) < 0.15
    out = dst.read_bytes()
    assert out[:trim._id3v2_size(data)] == data[:trim._id3v2_size(data)]  # tags byte for byte


@needs_ffmpeg
def test_fades_are_quiet_at_the_ends(tmp_path):
    src, dst = tmp_path / "a.mp3", tmp_path / "b.mp3"
    _make(src)
    trim.trim_file(FFMPEG, str(src), str(dst), 1.0, 9.0, fade_in=2.0, fade_out=2.0)
    pcm = _decode(dst)
    middle = _rms(pcm[3 * 8000:5 * 8000])
    assert _rms(pcm[200:1200]) < middle * 0.25        # the first moments: much quieter
    assert _rms(pcm[-1200:-200]) < middle * 0.25      # the last moments too
    assert middle * 0.3 < _rms(pcm[8000 + 4000:8000 + 6000]) < middle * 0.95  # half way through the fade in


@needs_ffmpeg
def test_no_change_when_nothing_is_cut(tmp_path):
    src, dst = tmp_path / "a.mp3", tmp_path / "b.mp3"
    _make(src, 4)
    trim.trim_file(FFMPEG, str(src), str(dst), 0, None)
    a, b = _decode(src), _decode(dst)
    assert abs(len(a) - len(b)) < 400


@needs_ffmpeg
def test_cbr_and_crc(tmp_path):
    src, dst = tmp_path / "a.mp3", tmp_path / "b.mp3"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=6", "-ac", "1",
                    "-c:a", "libmp3lame", "-b:a", "128k", str(src)], check=True)
    trim.trim_file(FFMPEG, str(src), str(dst), 1.0, 5.0, fade_out=1.0)
    assert abs(len(_decode(dst)) / 8000 - 4.0) < 0.15


def test_crc16_known_value():
    assert trim._crc16(b"123456789") == 0xAEE7  # MPEG audio's CRC (poly 0x8005, start 0xFFFF): "CRC-16/CMS"


@needs_ffmpeg
def test_flac(tmp_path):
    src, dst = tmp_path / "a.flac", tmp_path / "b.flac"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
                    "-metadata", "title=Flac song", str(src)], check=True)
    trim.trim_file(FFMPEG, str(src), str(dst), 1.0, 6.0, 1.0, 1.0)
    from mutagen.flac import FLAC

    f = FLAC(dst)
    assert f["title"] == ["Flac song"] and abs(f.info.length - 5.0) < 0.05


@needs_ffmpeg
def test_in_place_sends_original_to_recycle_bin(tmp_path, monkeypatch):
    src = tmp_path / "a.mp3"
    _make(src, 5)
    binned = []
    from music_manager.core import fileops

    def recycle(paths):
        for p in paths:
            binned.append(p)
            os.remove(p)
        return []

    monkeypatch.setattr(fileops, "recycle", recycle)
    trim.trim_in_place(FFMPEG, str(src), 1.0, 4.0)
    assert binned == [str(src)] and src.exists() and not (tmp_path / "a.trimming.mp3").exists()
    assert abs(trim.mp3_duration(src.read_bytes()) - 3.0) < 0.1


@needs_ffmpeg
def test_peaks(tmp_path):
    src = tmp_path / "a.mp3"
    _make(src, 3)
    p, length = trim.peaks(FFMPEG, str(src), 100)
    assert len(p) <= 100 and abs(length - 3) < 0.2 and max(p) > 0.05


@needs_ffmpeg
def test_trim_window(tmp_path):
    import time

    from PySide6.QtWidgets import QApplication

    from media_manager.trim_window import TrimWindow, clock, parse_clock

    QApplication.instance() or QApplication([])

    assert clock(328.04) == "5:28.0" and parse_clock("5:28.0") == 328.0 and parse_clock("12.5") == 12.5
    src = tmp_path / "a.mp3"
    _make(src, 6)
    dlg = TrimWindow(FFMPEG, str(src))
    until = time.time() + 10
    while dlg.wave.length <= 0 and time.time() < until:
        QApplication.processEvents()
        time.sleep(0.02)
    assert not dlg.ok.isEnabled()  # nothing changed yet
    assert dlg.values()[1] is None
    dlg.start_box.setText("0:01.5")
    dlg.end_box.setText("0:05.0")
    dlg._typed()
    dlg.fade_out_box.setValue(1.0)
    assert dlg.values() == (1.5, 5.0, 0.0, 1.0) and dlg.ok.isEnabled()
    assert "after the trim" in dlg.meta.text()


@needs_ffmpeg
def test_trim_from_music(tmp_path, monkeypatch):
    import time

    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from media_manager import trim_window
    from media_manager.app import build_window
    from music_manager.core import fileops, tags
    from music_manager.core.settings import Settings as MusicSettings

    for name in ("Review", "Library"):
        (tmp_path / name).mkdir()
    m = MusicSettings.load()
    m.review_folder, m.library_folder = str(tmp_path / "Review"), str(tmp_path / "Library")
    m.save()
    song = tmp_path / "Library" / "Someone - Song.mp3"
    _make(song, 6)
    win = build_window()
    music = win.music
    track = tags.read_track(str(song))
    monkeypatch.setattr(music, "selected_tracks", lambda: [track])
    assert [t for t, _ in music.extra_menu_items([track])] == ["✂ Trim… (Ctrl+T)"]
    monkeypatch.setattr(trim_window.TrimWindow, "exec", lambda self: True)
    monkeypatch.setattr(trim_window.TrimWindow, "values", lambda self: (1.0, 4.0, 0.5, 0.5))
    binned = []
    monkeypatch.setattr(fileops, "recycle", lambda paths: [binned.append(p) or os.remove(p) for p in paths] and [])
    win.trim_song()
    end = time.time() + 20
    while "Trimmed" not in music.status.text() and time.time() < end:
        QApplication.processEvents()
        time.sleep(0.02)
    assert "Trimmed" in music.status.text(), music.status.text()
    assert binned == [str(song)]
    assert abs(trim.mp3_duration(song.read_bytes()) - 3.0) < 0.1
    from mutagen.mp3 import MP3

    assert any("replaygain_track_gain" in k.lower() for k in MP3(song).tags.keys())  # measured again
    win.close()
