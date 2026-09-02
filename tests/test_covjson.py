from weather_data.covjson import coveragejson_to_records


def test_station_timeseries_covjson():
    payload = {
        "domain": {"axes": {"x": {"values": [10.0]}, "y": {"values": [50.0]}, "t": {"values": ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"]}}},
        "ranges": {
            "air_temperature": {"axisNames": ["t"], "shape": [2], "values": [273.15, 274.15]}
        },
    }
    records = coveragejson_to_records(payload)
    assert len(records) == 2
    assert records[0]["longitude"] == 10.0
    assert records[0]["latitude"] == 50.0
    assert records[1]["datetime"].hour == 1
