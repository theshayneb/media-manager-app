from media_manager.movies.watch import Watch, scan


def test_watch_learns_then_reports_new_and_forgets(tmp_path):
    folder = tmp_path / "Movies"
    folder.mkdir()
    (folder / "a.mkv").write_bytes(b"x")
    seen: dict = {}
    w = Watch(seen)
    found = scan([str(folder), str(tmp_path / "unplugged")])
    assert list(found) == [str(folder)]  # a missing drive is left out (not "everything was deleted")
    assert w.new(str(folder), found[str(folder)]) == []  # first look: learn
    (folder / "sub").mkdir()
    (folder / "sub" / "b.mp4").write_bytes(b"x")
    (folder / "notes.txt").write_text("not a video")
    assert w.new(str(folder), scan([str(folder)])[str(folder)]) == [str(folder / "sub" / "b.mp4")]
    w.mark_seen(str(folder), scan([str(folder)])[str(folder)])
    assert w.new(str(folder), scan([str(folder)])[str(folder)]) == []
    w.forget([])
    assert seen == {}
