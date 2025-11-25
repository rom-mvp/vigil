from flask import Flask, render_template_string
from pathlib import Path

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent


@app.route("/")
def index():
    html = (BASE_DIR / "index.html").read_text(encoding="utf-8")
    return render_template_string(html)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
