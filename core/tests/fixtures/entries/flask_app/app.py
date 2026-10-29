from flask import Flask

app = Flask(__name__)


def load_user(uid: int) -> dict:
    return {"id": uid}


@app.route("/users/<int:uid>")
def show_user(uid: int) -> dict:
    return load_user(uid)


@app.get("/health")
def health() -> str:
    return "ok"
