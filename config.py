import os
from datetime import timedelta


class Config:
    """Конфигурация приложения"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'database', 'educational_platform.db')

    # Настройки сессии
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    SESSION_COOKIE_SECURE = False  # True для production с HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Время жизни сессии
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    # Настройки загрузки файлов
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')

    # Настройки платформы
    PLATFORM_NAME = "EduSpace"
    DEFAULT_TIMEZONE = "Europe/Moscow"

    @staticmethod
    def init_app(app):
        """Инициализация приложения"""
        # Создаем необходимые директории
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(os.path.dirname(app.config['DATABASE_PATH']), exist_ok=True)


class DevelopmentConfig(Config):
    """Конфигурация для разработки"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Конфигурация для production"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    """Конфигурация для тестирования"""
    DEBUG = True
    TESTING = True
    DATABASE_PATH = ':memory:'  # Используем базу в памяти для тестов


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}