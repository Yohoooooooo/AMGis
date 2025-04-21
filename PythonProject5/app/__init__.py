from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
import pymysql
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Install PyMySQL as MySQLdb
pymysql.install_as_MySQLdb()

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-testing')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://flask_user:flask_password@localhost/business_system'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/uploads')
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes
    app.config['SQLALCHEMY_ECHO'] = True  # Log SQL queries

    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)

    # Register blueprints
    from app.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from app.main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from app.clients import clients as clients_blueprint
    app.register_blueprint(clients_blueprint, url_prefix='/clients')

    from app.rfqs import rfqs as rfqs_blueprint
    app.register_blueprint(rfqs_blueprint, url_prefix='/rfqs')

    from app.purchase_orders import purchase_orders as po_blueprint
    app.register_blueprint(po_blueprint, url_prefix='/purchase-orders')

    from app.admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')

    # Log app startup
    @app.before_request
    def before_first_request():
        app.logger.info("Application started")

    return app

