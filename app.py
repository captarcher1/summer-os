from flask import Flask
from config import Config
from database.models import init_db
from routes.dashboard import dashboard_bp
from routes.schedule import schedule_bp
from routes.xp import xp_bp
from routes.finance import finance_bp
from routes.parent import parent_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    init_db(app)

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(schedule_bp, url_prefix="/schedule")
    app.register_blueprint(xp_bp, url_prefix="/xp")
    app.register_blueprint(finance_bp, url_prefix="/finance")
    app.register_blueprint(parent_bp, url_prefix="/parent")

    return app


if __name__ == "__main__":
    app = create_app()
    # host='0.0.0.0' makes the app reachable from any device on your home network
    # Your son connects via http://<your-local-ip>:5000
    app.run(host="0.0.0.0", port=5000, debug=True)
