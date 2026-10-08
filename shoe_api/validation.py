from flask import abort, request, session
from functools import wraps


def body():
    value = request.get_json()
    if not isinstance(value, dict):
        abort(400, 'JSON body must be an object.')
    return value


def text(data, name, minimum=1, maximum=255):
    value = data.get(name)
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        abort(400, f'{name} must contain {minimum}–{maximum} characters.')
    return value


def positive_int(value, name, maximum=2147483647):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        abort(400, f'{name} must be a positive integer.')
    try:
        result = int(value)
    except (ValueError, TypeError):
        abort(400, f'{name} must be a positive integer.')
    if not 1 <= result <= maximum:
        abort(400, f'{name} must be between 1 and {maximum}.')
    return result


def login_required(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        if session.get('loggedin') != 'True' or not session.get('id'):
            abort(401, 'Please log in.')
        return func(*args, **kwargs)
    return wrapped
