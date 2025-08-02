import math
import socket
from datetime import datetime, timezone
from time import sleep, time

import pynmea2
import requests

vhost = "localhost"
vport = 8428

devices: list[str] = [
    "$GPDPT",
    "$GPGGA",
    "$GPHDG",
    "$GPHDT",
    "$GPMTW",
    "$GPMWV",
    "$GPRMC",
    "$GPROT",
    "$GPVHW",
    "$GPVLW",
    "$GPVTG",
    "$GPZDA",
]


def calculate_true_wind(aws, awa, vs):
    a = math.radians(awa)
    tw_x = aws * math.cos(a) - vs
    tw_y = aws * math.sin(a)
    tws = (tw_x**2 + tw_y**2) ** 0.5
    twa = (math.degrees(math.atan2(tw_y, tw_x)) + 360) % 360

    return round(tws, 2), round(twa, 2)


def handle_data(sorted_data, device_data, device):
    match device:
        case "$GPDPT":
            if device_data.depth:
                sorted_data["depth"] = device_data.depth

        case "$GPGGA":
            if device_data.lat:
                sorted_data["lat"] = device_data.lat

            if device_data.lat_dir:
                sorted_data["lat_dir"] = device_data.lat_dir

            if device_data.lon:
                sorted_data["lon"] = device_data.lon

            if device_data.lon_dir:
                sorted_data["lon_dir"] = device_data.lon_dir

            if device_data.num_sats:
                sorted_data["num_sats"] = device_data.num_sats

            if device_data.horizontal_dil:
                sorted_data["horizontal_dil"] = device_data.horizontal_dil

            if device_data.altitude:
                sorted_data["altitude"] = device_data.altitude

            if device_data.geo_sep:
                sorted_data["geo_sep"] = device_data.geo_sep

        case "$GPGSV":
            if device_data.geo_sep:
                sorted_data["geo_sep"] = device_data.geo_sep

        case "$GPHDG":
            if device_data.heading:
                sorted_data["heading"] = device_data.heading

        case "$GPMTW":
            if device_data.temperature:
                sorted_data["temperature"] = device_data.temperature

        case "$GPMWV":
            if device_data.wind_angle:
                sorted_data["AWA"] = device_data.wind_angle

            if device_data.wind_speed:
                sorted_data["AWS"] = device_data.wind_speed

        case "$GPRMC":
            if device_data.spd_over_grnd:
                sorted_data["speed"] = device_data.spd_over_grnd

            if device_data.true_course:
                sorted_data["true_course"] = device_data.true_course

            if device_data.mag_variation:
                sorted_data["mag_var"] = device_data.mag_variation

            if device_data.mag_var_dir:
                sorted_data["mag_var_dir"] = device_data.mag_var_dir

        case "$GPROT":
            if device_data.rate_of_turn:
                sorted_data["rate_of_turn"] = device_data.rate_of_turn

        case "$GPVHW":
            if device_data.heading_true:
                sorted_data["true_heading"] = device_data.heading_true

            if device_data.heading_magnetic:
                sorted_data["heading_magnetic"] = device_data.heading_magnetic

            if device_data.water_speed_knots:
                sorted_data["water_speed"] = device_data.water_speed_knots

        case "$GPVLW":
            if device_data.trip_distance:
                sorted_data["trip_distance"] = device_data.trip_distance

        case "$GPVTG":
            if device_data.true_track:
                sorted_data["true_track"] = device_data.true_track

            if device_data.mag_track:
                sorted_data["mag_track"] = device_data.mag_track

        case "$GPZDA":
            if device_data.local_zone:
                sorted_data["local_zone"] = device_data.local_zone


def send_data(sorted_data):
    sorted_data["TWS"], sorted_data["TWA"] = calculate_true_wind(
        float(sorted_data["AWS"]),
        float(sorted_data["AWA"]),
        float(sorted_data["speed"]),
    )

    labels = {"vessel": "Piryt"}
    label_str = ",".join([f'{k}="{v}"' for k, v in labels.items()])

    timestamp = int(time())

    lines = ""
    for key, value in sorted_data.items():
        lines += f"{key}{{{label_str}}} {value} {timestamp}\n"

    url = f"http://{vhost}:{vport}/api/v1/import/prometheus"
    response = requests.post(url, data=lines)
    print(response)


def data_saver(save_interval=5):
    sorted_data = {}
    ip = "192.168.76.51"
    port = 10110

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((ip, port))

        start = datetime.now(timezone.utc).timestamp()

        while True:
            data = s.recv(4096)  # Receive up to 4096 bytes
            if not data:
                continue

            data = data.decode("ascii")
            sentences = data.splitlines()[1:-1]

            for sentence in sentences:
                device = sentence[:6]

                if device not in devices:
                    continue

                device_data = pynmea2.parse(sentence)
                handle_data(sorted_data, device_data, device)

            now = datetime.now(timezone.utc).timestamp()

            if now - start > save_interval:
                send_data(sorted_data)

                start = math.floor(datetime.now(timezone.utc).timestamp())

            sleep(0.1)


def main():
    data_saver()


if __name__ == "__main__":
    main()
