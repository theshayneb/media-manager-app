"""Music › Trim: cut the start and/or end off a song, with a fade in / fade out (no Qt).

MP3s are NOT re-encoded (the user's rule). The cut is made between MP3 frames (1152 samples, about 1/40 s), and
fades lower each frame's own "global gain" (one step = 1.5 dB), as mp3DirectCut does. The tags (ID3v2 at the
start, ID3v1/APE at the end) are kept byte for byte; a VBR header (Xing/Info) is written again for the new length.
FLAC is lossless, so it is decoded and encoded again with ffmpeg (tags and pictures copied with mutagen).
"""

from __future__ import annotations

import array
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

_BITRATES = {
    1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],      # MPEG-1 Layer III
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],          # MPEG-2 / 2.5 Layer III
}
_RATES = {1: [44100, 48000, 32000], 2: [22050, 24000, 16000], 25: [11025, 12000, 8000]}
FORMATS = (".mp3", ".flac")


class TrimError(Exception):
    pass


def can_trim(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in FORMATS


# ---------------------------------------------------------------------------------------------- MP3 frames
@dataclass
class Frame:
    offset: int
    length: int
    version: int      # 1, 2 or 25 (2.5)
    crc: bool         # a CRC follows the header
    mono: bool
    rate: int

    @property
    def samples(self) -> int:
        return 1152 if self.version == 1 else 576

    @property
    def side_len(self) -> int:
        if self.version == 1:
            return 17 if self.mono else 32
        return 9 if self.mono else 17

    @property
    def side_start(self) -> int:  # within the frame
        return 6 if self.crc else 4


def _header(data: bytes | bytearray, pos: int) -> Frame | None:
    if pos + 4 > len(data) or data[pos] != 0xFF or (data[pos + 1] & 0xE0) != 0xE0:
        return None
    b2, b3, b4 = data[pos + 1], data[pos + 2], data[pos + 3]
    version = {3: 1, 2: 2, 0: 25}.get((b2 >> 3) & 3)
    if version is None or ((b2 >> 1) & 3) != 1:  # Layer III only
        return None
    br_index, sr_index = b3 >> 4, (b3 >> 2) & 3
    if br_index in (0, 15) or sr_index == 3:  # (free-format bitrates aren't handled)
        return None
    bitrate = _BITRATES[1 if version == 1 else 2][br_index] * 1000
    rate = _RATES[version][sr_index]
    pad = (b3 >> 1) & 1
    length = (144 if version == 1 else 72) * bitrate // rate + pad
    return Frame(pos, length, version, not (b2 & 1), (b4 >> 6) == 3, rate)


def _id3v2_size(data: bytes) -> int:
    if data[:3] != b"ID3" or len(data) < 10:
        return 0
    size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
    return 10 + size + (10 if data[5] & 0x10 else 0)


def _trailing_tags_start(data: bytes) -> int:
    """Where ID3v1 / APEv2 tags at the end of the file start."""
    end = len(data)
    if end >= 128 and data[end - 128:end - 125] == b"TAG":
        end -= 128
    if end >= 32 and data[end - 32:end - 24] == b"APETAGEX":
        size = int.from_bytes(data[end - 20:end - 16], "little")
        flags = int.from_bytes(data[end - 12:end - 8], "little")
        end -= size + (32 if flags & 0x80000000 else 0)
    return max(end, 0)


def _is_vbr_header(data: bytes, f: Frame) -> bool:
    at = f.offset + f.side_start + f.side_len
    return data[at:at + 4] in (b"Xing", b"Info") or data[f.offset + 36:f.offset + 40] == b"VBRI"


@dataclass
class Mp3:
    data: bytes
    head: int                 # where the audio starts (after ID3v2)
    tail: int                 # where the end tags start
    frames: list[Frame]       # the audio frames (not the VBR header)
    vbr: Frame | None         # the Xing/Info/VBRI frame, if there was one

    @property
    def frame_seconds(self) -> float:
        f = self.frames[0]
        return f.samples / f.rate

    @property
    def duration(self) -> float:
        return len(self.frames) * self.frame_seconds


def parse(data: bytes) -> Mp3:
    head = _id3v2_size(data)
    tail = _trailing_tags_start(data)
    frames: list[Frame] = []
    pos = head
    while pos < tail:
        f = _header(data, pos)
        if f is None or pos + f.length > tail:
            # not a frame here: on to the next place where two frames follow each other (junk is left out)
            nxt, found = pos + 1, False
            while nxt < tail:
                g = _header(data, nxt)
                if g and nxt + g.length <= tail and (nxt + g.length == tail or _header(data, nxt + g.length)):
                    found = True
                    break
                nxt += 1
            if not found:
                break
            pos = nxt
            continue
        frames.append(f)
        pos += f.length
    if not frames:
        raise TrimError("No MP3 audio found in the file")
    vbr = frames[0] if _is_vbr_header(data, frames[0]) else None
    if vbr:
        frames = frames[1:]
    if not frames:
        raise TrimError("No MP3 audio found in the file")
    return Mp3(data, head, tail, frames, vbr)


# ---------------------------------------------------------------------------------------------- bits
def _get(buf: bytearray, bit: int, n: int) -> int:
    v = 0
    for i in range(n):
        b = bit + i
        v = (v << 1) | ((buf[b >> 3] >> (7 - (b & 7))) & 1)
    return v


def _put(buf: bytearray, bit: int, n: int, value: int) -> None:
    for i in range(n):
        b = bit + i
        on = (value >> (n - 1 - i)) & 1
        if on:
            buf[b >> 3] |= 1 << (7 - (b & 7))
        else:
            buf[b >> 3] &= ~(1 << (7 - (b & 7))) & 0xFF


def _crc16(data: bytes | bytearray) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x8005) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def _granules(f: Frame) -> list[int]:
    """The bit position (in the side info) of each granule/channel block."""
    nch = 1 if f.mono else 2
    if f.version == 1:
        start, size, count = 9 + (5 if f.mono else 3) + 4 * nch, 59, 2 * nch
    else:
        start, size, count = 8 + (1 if f.mono else 2), 63, nch
    return [start + i * size for i in range(count)]


def _main_data_begin(frame: bytearray, f: Frame) -> int:
    side = f.side_start
    return _get(frame, side * 8, 9 if f.version == 1 else 8)


def _fix_crc(frame: bytearray, f: Frame) -> None:
    if f.crc:
        crc = _crc16(bytes(frame[2:4]) + bytes(frame[6:6 + f.side_len]))
        frame[4], frame[5] = crc >> 8, crc & 0xFF


def _quieter(frame: bytearray, f: Frame, steps: int) -> None:
    """Lower the frame's volume by steps × 1.5 dB (a very large number: silent)."""
    if steps <= 0:
        return
    base = f.side_start * 8
    for g in _granules(f):
        at = base + g + 21
        gain = _get(frame, at, 8)
        _put(frame, at, 8, max(0, gain - steps) if steps < 200 else 0)
    _fix_crc(frame, f)


def _silence(frame: bytearray, f: Frame) -> None:
    """No sound at all from this frame (it reads none of its audio data)."""
    base = f.side_start * 8
    for g in _granules(f):
        _put(frame, base + g, 12 + 9 + 8, 0)  # part2_3_length, big_values, global_gain
    _fix_crc(frame, f)


def _fade_steps(fraction: float) -> int:
    """Gain steps (1.5 dB each) for a volume of fraction (0…1, an even, linear fade)."""
    if fraction >= 1:
        return 0
    if fraction <= 0.001:
        return 255
    return round(-20 * math.log10(fraction) / 1.5)


def _vbr_frame(mp3: Mp3, kept: list[bytes]) -> bytes:
    """The old Xing/Info frame with the new frame count, length and seek table (no LAME extension)."""
    assert mp3.vbr is not None
    f = mp3.vbr
    old = mp3.data[f.offset:f.offset + f.length]
    at = f.side_start + f.side_len
    out = bytearray(f.length)
    out[:4] = old[:4]
    if old[at:at + 4] == b"Info" or old[36:40] == b"VBRI":
        tag = b"Info" if old[at:at + 4] == b"Info" else b"Xing"
    else:
        tag = b"Xing"
    total = f.length + sum(len(k) for k in kept)
    with_toc = at + 16 + 100 <= f.length
    out[at:at + 4] = tag
    out[at + 4:at + 8] = (7 if with_toc else 3).to_bytes(4, "big")
    out[at + 8:at + 12] = len(kept).to_bytes(4, "big")
    out[at + 12:at + 16] = total.to_bytes(4, "big")
    if with_toc:
        starts, pos = [], f.length
        for k in kept:
            starts.append(pos)
            pos += len(k)
        for i in range(100):
            n = min(len(kept) - 1, int(i / 100 * len(kept)))
            out[at + 16 + i] = min(255, int(starts[n] / total * 256)) if kept else 0
    _fix_crc(out, f)
    return bytes(out)


def trim_mp3_bytes(data: bytes, start: float, end: float | None, fade_in: float = 0, fade_out: float = 0) -> bytes:
    """The song from start to end (seconds), faded in/out over those many seconds, without re-encoding."""
    mp3 = parse(data)
    sec = mp3.frame_seconds
    first = max(0, round(start / sec))
    last = len(mp3.frames) if end is None else min(len(mp3.frames), round(end / sec))
    if last - first < 2:
        raise TrimError("Nothing would be left of the song")
    n = last - first
    kept: list[bytes] = []
    available = 0  # audio bytes of the frames kept so far (the bit reservoir the next frame may use)
    for i, f in enumerate(mp3.frames[first:last]):
        frame = bytearray(data[f.offset:f.offset + f.length])
        if _main_data_begin(frame, f) > available:
            _silence(frame, f)  # its sound started in a frame that's cut off: silent, not a click
        else:
            t_in, t_out = (i + 0.5) * sec, (n - i - 0.5) * sec  # this frame's middle, from each end
            fraction = 1.0
            if fade_in > 0 and t_in < fade_in:
                fraction = min(fraction, t_in / fade_in)
            if fade_out > 0 and t_out < fade_out:
                fraction = min(fraction, t_out / fade_out)
            _quieter(frame, f, _fade_steps(fraction))
        available += f.length - f.side_start - f.side_len
        kept.append(bytes(frame))
    head = data[:mp3.head]
    vbr = _vbr_frame(mp3, kept) if mp3.vbr else b""
    return head + vbr + b"".join(kept) + data[mp3.tail:]


def mp3_duration(data: bytes) -> float:
    return parse(data).duration


# ---------------------------------------------------------------------------------------------- whole songs
def trim_file(ffmpeg: str | None, src: str, dst: str, start: float, end: float | None,
              fade_in: float = 0, fade_out: float = 0) -> None:
    """Write the trimmed song to dst (src isn't changed)."""
    ext = os.path.splitext(src)[1].lower()
    if ext == ".mp3":
        out = trim_mp3_bytes(Path(src).read_bytes(), start, end, fade_in, fade_out)
        Path(dst).write_bytes(out)
        _drop_length_tag(dst)
    elif ext == ".flac":
        _trim_flac(ffmpeg, src, dst, start, end, fade_in, fade_out)
    else:
        raise TrimError("Only MP3 and FLAC songs can be trimmed")


def _drop_length_tag(path: str) -> None:
    """An ID3 TLEN (length) would still say the old length."""
    try:
        from mutagen.id3 import ID3, ID3NoHeaderError

        tags = ID3(path)
        if "TLEN" in tags:
            tags.delall("TLEN")
            tags.save(path, v2_version=tags.version[1] if tags.version[1] in (3, 4) else 3)
    except (ID3NoHeaderError, OSError, ValueError):
        pass
    except Exception:  # noqa: BLE001 - a tag we can't read is left as it is
        pass


def _trim_flac(ffmpeg: str | None, src: str, dst: str, start: float, end: float | None,
               fade_in: float, fade_out: float) -> None:
    from music_manager.core.ffmpeg import FfmpegError, last_lines, run

    if not ffmpeg:
        raise TrimError("ffmpeg wasn't found")
    length = (end if end is not None else flac_duration(src)) - start
    if length <= 0.05:
        raise TrimError("Nothing would be left of the song")
    chain = [f"atrim=start={start:.4f}" + (f":end={end:.4f}" if end is not None else ""), "asetpts=PTS-STARTPTS"]
    if fade_in > 0:
        chain.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    if fade_out > 0:
        chain.append(f"afade=t=out:st={max(0.0, length - fade_out):.3f}:d={fade_out:.3f}")
    proc = run(ffmpeg, ["-y", "-i", src, "-map", "0:a:0", "-af", ",".join(chain), "-map_metadata", "-1",
                        "-c:a", "flac", dst])
    if proc.returncode != 0:
        raise FfmpegError(f"couldn't trim it: {last_lines(proc.stderr_text)}")  # type: ignore[attr-defined]
    from mutagen.flac import FLAC

    old, new = FLAC(src), FLAC(dst)
    new.delete()
    if old.tags:
        for key, values in old.tags.as_dict().items():
            new[key] = values
    new.clear_pictures()
    for pic in old.pictures:
        new.add_picture(pic)
    new.save()


def flac_duration(path: str) -> float:
    from mutagen.flac import FLAC

    return float(FLAC(path).info.length)


def duration(path: str) -> float:
    if path.lower().endswith(".mp3"):
        return mp3_duration(Path(path).read_bytes())
    return flac_duration(path)


def peaks(ffmpeg: str, path: str, count: int = 800) -> tuple[list[float], float]:
    """The waveform: count loudness peaks (0…1) and the length in seconds."""
    from music_manager.core.ffmpeg import FfmpegError, last_lines, run

    rate = 4000
    proc = run(ffmpeg, ["-i", path, "-map", "0:a:0", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"])
    if proc.returncode != 0 or not proc.stdout:
        raise FfmpegError(f"couldn't read the song: {last_lines(proc.stderr_text)}")  # type: ignore[attr-defined]
    samples = array.array("h")
    samples.frombytes(proc.stdout[: len(proc.stdout) // 2 * 2])
    n = len(samples)
    step = max(1, -(-n // count))
    out = []
    for i in range(0, n, step):
        chunk = samples[i:i + step]
        out.append(max(max(chunk), -min(chunk)) / 32768 if chunk else 0.0)
    return out[:count], n / rate


def trim_in_place(ffmpeg: str | None, path: str, start: float, end: float | None,
                  fade_in: float = 0, fade_out: float = 0) -> None:
    """Trim the song itself: the trimmed copy is written beside it, the original goes to the Recycle Bin, and
    the copy takes its name (so the lyrics .txt, which goes by the name, still belongs to it)."""
    from music_manager.core import fileops

    folder, name = os.path.split(path)
    stem, ext = os.path.splitext(name)
    tmp = os.path.join(folder, f"{stem}.trimming{ext}")
    try:
        trim_file(ffmpeg, path, tmp, start, end, fade_in, fade_out)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    failed = fileops.recycle([path])
    if failed:
        os.remove(tmp)
        raise TrimError(f"Couldn't put the original in the Recycle Bin: {failed[0][1]}")
    os.replace(tmp, path)  # (if this failed, the trimmed copy stays beside it as "….trimming")


def preview_copy(ffmpeg: str | None, path: str, start: float, end: float | None,
                 fade_in: float, fade_out: float) -> str:
    """The trimmed song as a temporary file, to listen to before trimming."""
    ext = os.path.splitext(path)[1].lower()
    fd, tmp = tempfile.mkstemp(prefix="trim-preview-", suffix=ext)
    os.close(fd)
    trim_file(ffmpeg, path, tmp, start, end, fade_in, fade_out)
    return tmp
