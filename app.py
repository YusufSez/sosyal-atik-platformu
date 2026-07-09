from factory import create_app
from extensions import socketio

app = create_app()

if __name__ == "__main__":
    socketio.run(app, debug=app.config["DEBUG"], allow_unsafe_werkzeug=True)
