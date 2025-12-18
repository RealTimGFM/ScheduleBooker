# wsgi.py
app = None

try:
    # common pattern: app.py defines `app`
    from app import app as _app

    app = _app
except Exception:
    pass

if app is None:
    try:
        # common pattern: app.py defines `create_app()`
        from app import create_app

        app = create_app()
    except Exception:
        pass

if app is None:
    try:
        # common pattern: schedulebooker package defines create_app()
        from schedulebooker import create_app

        app = create_app()
    except Exception as e:
        raise RuntimeError(
            "Could not locate the Flask app. Expected app.py:app or create_app()."
        ) from e
