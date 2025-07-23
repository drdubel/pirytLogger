import threading

import psycopg
from flask import Flask, render_template

from credentials import db_name, db_user
from save_data import create_tables, data_saver

db_host = "localhost"
db_port = "5432"

app = Flask(__name__)


def get_data():
    with psycopg.connect(
        f"host={db_host} port={db_port} dbname={db_name} user={db_user}"
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM hourly_navigation_summary ORDER BY id DESC;")
            data = cur.fetchall()
            colnames = [desc[0] for desc in cur.description]

    return colnames, data


@app.route("/")
def index():
    columns, data = get_data()
    return render_template("index.html", columns=columns, data=data)


if __name__ == "__main__":
    import os

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        create_tables()
        threading.Thread(target=data_saver, daemon=True).start()

    app.run(debug=True, use_reloader=True, threaded=True)
