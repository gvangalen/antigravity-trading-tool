"""Celery package exports without eager worker bootstrap side effects."""


def __getattr__(name):
    if name == "celery":
        from .celery_app import app

        return app
    raise AttributeError(name)
