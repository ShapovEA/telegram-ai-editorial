from datetime import UTC, date, datetime, time

from app.domain.schemas import NewsSchedule, SmmSchedule
from app.services.schedule import label, news_grid, rezone, smm_grid, to_local, to_utc


def test_rezone_keeps_local_time():
    moved = rezone(datetime(2026, 10, 13, 16, 0, tzinfo=UTC), "Europe/Moscow", "Asia/Irkutsk")
    assert moved == datetime(2026, 10, 13, 11, 0, tzinfo=UTC)
    assert to_local(moved, "Asia/Irkutsk") == datetime(2026, 10, 13, 19, 0)


def test_rezone_follows_daylight_saving_of_new_zone():
    winter = rezone(datetime(2026, 12, 1, 15, 30, tzinfo=UTC), "Europe/Moscow", "Europe/Berlin")
    summer = rezone(datetime(2026, 7, 1, 15, 30, tzinfo=UTC), "Europe/Moscow", "Europe/Berlin")
    assert to_local(winter, "Europe/Berlin").time() == to_local(summer, "Europe/Berlin").time() == time(18, 30)
    assert (winter.hour, summer.hour) == (17, 16)


def test_rezoned_news_slots_land_on_new_grid():
    old, new = NewsSchedule(timezone="Europe/Moscow"), NewsSchedule(timezone="Asia/Irkutsk")
    moved = [rezone(t, old.timezone, new.timezone) for t in news_grid(old, datetime(2026, 10, 13, 0, 0, tzinfo=UTC), hours=36)]
    assert {to_local(t, new.timezone).time() for t in moved} == {time(9), time(14), time(19)}


def test_smm_grid_is_in_channel_zone():
    schedule = SmmSchedule(timezone="Asia/Irkutsk", posts_per_week=5)
    local = [to_local(t, schedule.timezone) for t in smm_grid(schedule, date(2026, 10, 12))]
    assert len(local) == 5
    assert all(t.weekday() < 5 and time(9) <= t.time() <= time(21) for t in local)
    assert [to_utc(t, schedule.timezone) for t in local] == smm_grid(schedule, date(2026, 10, 12))


def test_label_is_local_wall_time():
    assert label(datetime(2026, 10, 14, 18, 30)) == "Ср 14.10 18:30"
