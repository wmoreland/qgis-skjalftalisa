import requests
import json

url = "https://vi-api.vedur.is/skjalftalisa/v1/quakefilter"

headers = {
    "Content-Type": "application/json",
}

body = {
    "area": [
        [63.2, -24.6],
        [66.6, -24.6],
        [66.6, -13.4],
        [63.2, -13.4],
    ],
    "depth_max": 35,
    "depth_min": 5,
    "end_time": "2024-12-19 10:00:00",
    "event_type": ["qu"],
    "magnitude_preference": ["Mlw"],
    "originating_system": ["SIL picks"],
    "size_max": 7,
    "size_min": -3,
    "start_time": "2024-12-12 10:00:00",
}

response = requests.post(url, headers=headers, json=body)

if response.status_code == 200:
    quake_data = response.json()
    geojson_data = {
        "type": "FeatureCollection",
        "features": quake_data,
    }
    print(geojson_data)
    with open("earthquakes.geojson", "w") as file:
        json.dump(geojson_data, file, indent=2)
else:
    print(f"Error: {response.status_code} - {response.text}")
