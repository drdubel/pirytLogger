import math
import socket
from datetime import datetime, timedelta, timezone
from time import sleep

import psycopg
import pynmea2

from credentials import db_name, db_user

db_host = "localhost"
db_port = 5432

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


def create_tables():
    with psycopg.connect(
        f"host={db_host} port={db_port} dbname={db_name} user={db_user}"
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS navigation_data (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ DEFAULT NOW(),
                    rate_of_turn REAL,
                    heading REAL,
                    AWA REAL,
                    AWS REAL,
                    true_track REAL,
                    mag_track REAL,
                    speed REAL,
                    true_course REAL,
                    mag_var REAL,
                    mag_var_dir VARCHAR(2),
                    true_heading REAL,
                    heading_magnetic REAL,
                    water_speed REAL,
                    temperature REAL,
                    depth REAL,
                    trip_distance REAL,
                    lat REAL,
                    lat_dir VARCHAR(2),
                    lon REAL,
                    lon_dir VARCHAR(2),
                    num_sats INTEGER,
                    horizontal_dil REAL,
                    altitude REAL,
                    geo_sep REAL,
                    TWA REAL,
                    TWS REAL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS hourly_navigation_summary (
                    id SERIAL PRIMARY KEY,
                    hour TIMESTAMPTZ DEFAULT NOW(),
                    TWA REAL,
                    TWS REAL,
                    AWA REAL,
                    AWS REAL,
                    Heading REAL,
                    Speed REAL,
                    Altitude REAL,
                    Lattitude REAL,
                    LatDir VARCHAR(2),
                    Longitude REAL,
                    LonDir VARCHAR(2),
                    Depth REAL,
                    Temp REAL
                );
                """
            )

        conn.commit()


def send_data(sorted_data):
    sorted_data["TWS"], sorted_data["TWA"] = (
        calculate_true_wind(
            float(sorted_data["AWS"]),
            float(sorted_data["AWA"]),
            float(sorted_data["speed"]),
        )
    )

    print(sorted_data.keys())

    with psycopg.connect(
        f"host={db_host} port={db_port} dbname={db_name} user={db_user}"
    ) as conn:
        with conn.cursor() as cur:
            columns = ", ".join(sorted_data.keys())
            placeholders = ", ".join(["%s"] * len(sorted_data))
            values = tuple(sorted_data.values())
            cur.execute(
                f"""
                INSERT INTO navigation_data ({columns})
                VALUES ({placeholders})
                """,
                values,
            )
        conn.commit()


def send_hourly_summary():
    with psycopg.connect(
        f"host={db_host} port={db_port} dbname={db_name} user={db_user}"
    ) as conn:
        with conn.cursor() as cur:
            time_to = datetime.now(timezone.utc).replace(
                minute=0, second=0, microsecond=0
            )
            time_from = time_to - timedelta(hours=1)
            print(f"Saving summary for {time_from} to {time_to}")

            # First, get averages and last row
            avg_query = """
                SELECT
                    ROUND(AVG(TWA::numeric), 2) AS TWA,
                    ROUND(AVG(TWS::numeric), 2) AS TWS,
                    ROUND(AVG(AWA::numeric), 2) AS AWA,
                    ROUND(AVG(AWS::numeric), 2) AS AWS,
                    ROUND(AVG(heading_magnetic::numeric), 2) AS Heading,
                    ROUND(AVG(speed::numeric), 2) AS Speed
                FROM navigation_data
                WHERE timestamp >= %s AND timestamp < %s;
            """
            cur.execute(avg_query, (time_from, time_to))
            avg_result = cur.fetchone()

            last_row_query = """
                SELECT
                    altitude,
                    lat,
                    lat_dir,
                    lon,
                    lon_dir,
                    depth,
                    temperature
                FROM navigation_data
                WHERE timestamp >= %s AND timestamp < %s
                ORDER BY timestamp DESC
                LIMIT 1;
            """
            cur.execute(last_row_query, (time_from, time_to))
            last_row = cur.fetchone()

            insert_query = """
                INSERT INTO hourly_navigation_summary (
                    Hour,
                    TWA,
                    TWS,
                    AWA,
                    AWS,
                    Heading,
                    Speed,
                    Altitude,
                    Lattitude,
                    LatDir,
                    Longitude,
                    LonDir,
                    Depth,
                    Temp
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            values = (
                time_from,
                *(avg_result if avg_result else (None,) * 6),
                *(last_row if last_row else (None,) * 7),
            )

            print(values)
            cur.execute(insert_query, values)
            print(f"Saved summary for {time_from} to {time_to}")


def data_saver(save_interval=20):
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

                if int(now) % 3600 < save_interval:
                    send_hourly_summary()

                start = math.floor(datetime.now(timezone.utc).timestamp())

            sleep(0.1)


def main():
    create_tables()
    data_saver()


if __name__ == "__main__":
    main()
