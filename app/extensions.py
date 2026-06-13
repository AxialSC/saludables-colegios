"""
app/extensions.py — Instancias de extensiones (patron AXIAL).
Se inicializan en el Application Factory (app/__init__.py).
"""
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_wtf import CSRFProtect

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
csrf = CSRFProtect()
