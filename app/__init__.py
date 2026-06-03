from flask import Flask

from .config import Config
from .db import close_db, init_app
from .routes import bp as api_bp
from .views import bp as view_bp


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_class)

    init_app(app)
    app.teardown_appcontext(close_db)

    app.register_blueprint(view_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    return app
