import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'saheltahalk-baccalaureate-super-secret-key-2026')
    DATABASE_PATH = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saheltahalk.db'))
    DATABASE_URL = os.environ.get('DATABASE_URL')
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
