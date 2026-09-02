import datetime as dt

from weather_data.opera import MeteoGateDownloader


def test_opera_timestamp_snapping():
    downloader = MeteoGateDownloader.__new__(MeteoGateDownloader)
    value = dt.datetime(2026, 1, 1, 12, 14, 42, 123456)
    snapped = downloader.snap_timestamp(value, "RATE")
    assert snapped == dt.datetime(2026, 1, 1, 12, 0)
