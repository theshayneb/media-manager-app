import os

import pytest

from media_manager.movies import files
from media_manager.movies.naming import companion_target, episode_name, plex_name


@pytest.mark.parametrize("name, expected", [
    ("Show.Name.S01E02.Episode.Title.720p.WEB.mkv", "Show Name - S01E02 - Episode Title.mkv"),
    ("Doctor.Who.2005.S10E01.The.Pilot.1080p.mkv", "Doctor Who (2005) - S10E01 - The Pilot.mkv"),
    ("Show Name 1x02.mkv", "Show Name - S01E02.mkv"),
    ("show_name_s3e7_hdtv_x264-grp.mp4", "show name - S03E07.mp4"),
])
def test_episode_names(name, expected):
    assert episode_name(name) == expected


def test_movie_names():
    assert plex_name("Some.Movie.2019.1080p.BluRay.x264-GRP.mkv", "movies") == "Some Movie (2019).mkv"
    assert plex_name("Show.S01E02.mkv", "movies") is None  # an episode isn't renamed as a movie
    assert plex_name("Holiday clip.mp4", "tv") is None


def test_companion_target():
    target = companion_target(os.path.join("m", "Old.en.srt"), os.path.join("m", "Old.mkv"),
                              os.path.join("m", "New (2019).mkv"))
    assert target == os.path.join("m", "New (2019).en.srt")


def test_list_rename_move_delete(tmp_path, monkeypatch):
    movies = tmp_path / "Movies"
    (movies / "Sub").mkdir(parents=True)
    (movies / "Some.Movie.2019.1080p.mkv").write_bytes(b"x" * 10)
    (movies / "Some.Movie.2019.1080p.en.srt").write_text("1")
    (movies / "Sub" / "Other.Film.2001.mp4").write_bytes(b"y")
    (movies / "notes.txt").write_text("not a video")
    (movies / "Sample").mkdir()
    (movies / "Sample" / "sample.mkv").write_bytes(b"z")

    videos = files.list_videos(str(movies))
    assert [v.name for v in videos] == ["Some.Movie.2019.1080p.mkv", "Other.Film.2001.mp4"]  # by path

    plan = files.rename_plan(videos, "movies")
    targets = {os.path.basename(v.path): dest and os.path.basename(dest) for v, dest, _ in plan}
    assert targets == {"Other.Film.2001.mp4": "Other Film (2001).mp4",
                       "Some.Movie.2019.1080p.mkv": "Some Movie (2019).mkv"}

    done, failures = files.rename({v.path: dest for v, dest, _ in plan if dest})
    assert not failures and len(done) == 2
    assert (movies / "Some Movie (2019).mkv").exists() and (movies / "Some Movie (2019).en.srt").exists()
    assert (movies / "Sub" / "Other Film (2001).mp4").exists()

    # A second plan finds nothing to do.
    assert all(dest is None for _v, dest, _n in files.rename_plan(files.list_videos(str(movies)), "movies"))

    elsewhere = tmp_path / "Elsewhere"
    elsewhere.mkdir()
    done, failures = files.move([str(movies / "Some Movie (2019).mkv")], str(elsewhere))
    assert not failures
    assert (elsewhere / "Some Movie (2019).mkv").exists() and (elsewhere / "Some Movie (2019).en.srt").exists()

    trashed = []
    monkeypatch.setattr(files, "send2trash", lambda p: trashed.append(os.path.basename(p)))
    assert files.recycle([str(elsewhere / "Some Movie (2019).mkv")]) == []
    assert trashed == ["Some Movie (2019).mkv", "Some Movie (2019).en.srt"]


def test_rename_never_overwrites(tmp_path):
    (tmp_path / "A.Film.2010.mkv").write_bytes(b"1")
    (tmp_path / "A Film (2010).mkv").write_bytes(b"2")
    plan = files.rename_plan(files.list_videos(str(tmp_path)), "movies")
    dests = [d for _v, d, _n in plan if d]
    assert dests and all(os.path.basename(d) != "A Film (2010).mkv" for d in dests)
