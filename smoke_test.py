from weather_data.covjson import coveragejson_to_records

payload = {
    "domain": {"axes": {"x": {"values": [10]}, "y": {"values": [50]}, "t": {"values": ["2026-01-01T00:00:00Z"]}}},
    "ranges": {"air_temperature": {"axisNames": ["t"], "shape": [1], "values": [273.15]}},
}
assert coveragejson_to_records(payload)[0]["longitude"] == 10
print("Smoke test OK")
