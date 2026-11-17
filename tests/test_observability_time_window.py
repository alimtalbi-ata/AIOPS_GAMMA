"""Timezone validation for bounded observability searches."""
from datetime import datetime, timedelta, timezone, tzinfo

import pytest
from pydantic import ValidationError

from app.schemas import TimeWindow


class UndefinedOffset(tzinfo):
    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None

    def tzname(self, dt):
        return "undefined"


@pytest.mark.parametrize("bad_start", [True, False])
def test_time_window_rejects_timezone_without_utc_offset(bad_start):
    aware = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    undefined = datetime(2026, 11, 10, 11, tzinfo=UndefinedOffset())
    start, end = (undefined, aware) if bad_start else (aware, undefined)
    with pytest.raises(ValidationError, match="timezone-aware"):
        TimeWindow(start=start, end=end)


def test_time_window_accepts_distinct_utc_offsets():
    start = datetime(2026, 11, 10, 12, tzinfo=timezone(timedelta(hours=1)))
    end = datetime(2026, 11, 10, 12, 30, tzinfo=timezone.utc)
    assert TimeWindow(start=start, end=end).end == end


def test_time_window_rejects_nonincreasing_instants_across_offsets():
    start = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    end = datetime(2026, 11, 10, 12, 30, tzinfo=timezone(timedelta(hours=1)))
    with pytest.raises(ValidationError, match="increasing"):
        TimeWindow(start=start, end=end)
