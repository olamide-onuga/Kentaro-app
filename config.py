import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'), override=True)

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret')
    
    # SQLAlchemy configuration
    raw_db_uri = os.environ.get('DATABASE_URL', '').strip()
    is_production = bool(
        os.environ.get('RENDER') or 
        os.environ.get('DYNO') or 
        os.environ.get('RAILWAY_ENVIRONMENT') or 
        os.environ.get('FLASK_CONFIG') == 'production'
    )

    if raw_db_uri and is_production:
        # In cloud hosting (Render, Railway, Heroku), always use the provided DATABASE_URL
        db_uri = raw_db_uri
        if db_uri.startswith("postgres://"):
            db_uri = db_uri.replace("postgres://", "postgresql://", 1)
    elif raw_db_uri and not ('dpg-' in raw_db_uri and not is_production):
        # External postgres connection when accessible
        db_uri = raw_db_uri
        if db_uri.startswith("postgres://"):
            db_uri = db_uri.replace("postgres://", "postgresql://", 1)
    else:
        # Local development defaults to SQLite
        db_uri = 'sqlite:///' + os.path.join(basedir, 'kentaro.db')
        
    SQLALCHEMY_DATABASE_URI = db_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configure engine options per database driver
    if db_uri.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'connect_args': {
                'timeout': 30,
                'check_same_thread': False
            }
        }
    else:
        # PostgreSQL production connection pooling options
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': 10,
            'max_overflow': 20,
            'pool_recycle': 1800,
            'pool_pre_ping': True
        }
    
    # Paystack configuration
    PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY')
    PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY')
    
    # Flask-Mail configuration
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'False') == 'True'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', MAIL_USERNAME)

    # Upload configuration
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size

class DevelopmentConfig(Config):
    DEBUG = True
    
class ProductionConfig(Config):
    DEBUG = False
    
class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
