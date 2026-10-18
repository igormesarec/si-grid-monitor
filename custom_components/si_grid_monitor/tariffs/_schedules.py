"""Official hourly tables transcribed from cited URO/PISRS sources."""

from .models import DayType, ScheduleKey, Season


def _hours(*ranges: tuple[int, int, int]) -> tuple[int, ...]:
    result = [0] * 24
    for start, end, block in ranges:
        for hour in range(start, end):
            result[hour] = block
    if any(block == 0 for block in result):
        raise ValueError("tariff schedule must classify all 24 hours")
    return tuple(result)


SCHEDULE_2026: dict[ScheduleKey, tuple[int, ...]] = {
    (Season.HIGHER, DayType.WORKING): _hours(
        (0, 6, 3), (6, 7, 2), (7, 14, 1), (14, 16, 2), (16, 20, 1), (20, 22, 2), (22, 24, 3)
    ),
    (Season.HIGHER, DayType.NONWORKING): _hours(
        (0, 6, 4), (6, 7, 3), (7, 14, 2), (14, 16, 3), (16, 20, 2), (20, 22, 3), (22, 24, 4)
    ),
    (Season.LOWER, DayType.WORKING): _hours(
        (0, 6, 4), (6, 7, 3), (7, 14, 2), (14, 16, 3), (16, 20, 2), (20, 22, 3), (22, 24, 4)
    ),
    (Season.LOWER, DayType.NONWORKING): _hours(
        (0, 6, 5), (6, 7, 4), (7, 14, 3), (14, 16, 4), (16, 20, 3), (20, 22, 4), (22, 24, 5)
    ),
}


SCHEDULE_2027: dict[ScheduleKey, tuple[int, ...]] = {
    (Season.HIGHER, DayType.WORKING): _hours(
        (0, 6, 3), (6, 12, 1), (12, 17, 2), (17, 20, 1), (20, 22, 2), (22, 24, 3)
    ),
    (Season.HIGHER, DayType.NONWORKING): _hours(
        (0, 6, 4), (6, 12, 3), (12, 17, 4), (17, 22, 3), (22, 24, 4)
    ),
    (Season.LOWER, DayType.WORKING): _hours(
        (0, 6, 5), (6, 12, 3), (12, 17, 4), (17, 22, 3), (22, 24, 5)
    ),
    (Season.LOWER, DayType.NONWORKING): _hours(
        (0, 6, 5), (6, 12, 4), (12, 17, 5), (17, 22, 4), (22, 24, 5)
    ),
}
