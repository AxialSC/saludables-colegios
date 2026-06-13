"""
run.py — Arranque LOCAL para desarrollo.
Uso:  python run.py
(En PythonAnywhere NO se usa este archivo, se usa el WSGI.)
"""
from app import create_app

app = create_app('dev')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
