import json
from types import SimpleNamespace

from media_manager import phone_steam


def test_request_is_pending_until_answered(tmp_path):
    assert phone_steam.pending_request(tmp_path) is None
    (tmp_path / phone_steam.FOLDER).mkdir(parents=True)
    (tmp_path / phone_steam.REQUEST).write_text(json.dumps({"id": "a1"}))
    assert phone_steam.pending_request(tmp_path) == "a1"
    phone_steam.write_result(tmp_path, "a1", "running")
    assert phone_steam.pending_request(tmp_path) == "a1"  # (a PC closed mid-import tries again)
    phone_steam.write_result(tmp_path, "a1", "done", imported=2)
    assert phone_steam.pending_request(tmp_path) is None
    assert json.loads((tmp_path / phone_steam.RESULT).read_text())["imported"] == 2
    (tmp_path / phone_steam.REQUEST).write_text(json.dumps({"id": "b2"}))
    assert phone_steam.pending_request(tmp_path) == "b2"


def test_summary_counts_games():
    shot = lambda g: SimpleNamespace(game=g)  # noqa: E731
    s = phone_steam.summary([(shot("Hades"), "x"), (shot("Hades"), "y"), (shot("Celeste"), "z")], [("p", "locked")])
    assert s == {"imported": 3, "failed": 1, "games": {"Hades": 2, "Celeste": 1}, "problem": "locked"}


def test_plan_needs_a_destination():
    import pytest
    with pytest.raises(ValueError):
        phone_steam.plan(SimpleNamespace(steam_dest=""))


def test_run_imports_new_screenshots_once(tmp_path):
    shots = tmp_path / "deck" / "1145360" / "screenshots"
    shots.mkdir(parents=True)
    (shots / "20261104213012_1.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    dest = tmp_path / "Steam"
    dest.mkdir()
    settings = SimpleNamespace(steam_dest=str(dest), steam_path=str(tmp_path / "none"), steam_account="",
                               steam_extra_folders=[str(tmp_path / "deck")], steam_game_names={"1145360": "Hades"},
                               templates=[], path=tmp_path / "settings.json", steam_set_date=False,
                               steam_keyword=False, save=lambda: None)
    done, failures = phone_steam.run(settings, None)
    assert len(done) == 1 and not failures
    assert phone_steam.summary(done, failures)["games"] == {"Hades": 1}
    assert phone_steam.run(settings, None) == ([], [])  # imported before: not again
