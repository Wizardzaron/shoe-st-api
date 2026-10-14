#The purpose of this file is to have reusable functions that can be used across the backend


from flask import abort, request, session
from functools import wraps

#We replaced retrieving args with bodies as it's much safer due to urls being logged along with any parameters

def body():
    value = request.get_json()
    if not isinstance(value, dict):
        abort(400, 'JSON body must be an object.')
    return value

#Checks to see if the string being passed in from the frontend is between 1 to 255 characters so that its valid, helps prevent against unecessary queries to the db and against bots

def text(data, name, minimum=1, maximum=255):
    value = data.get(name)
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        abort(400, f'{name} must contain {minimum}–{maximum} characters.')
    return value


#Ensures that integer values are always positive to ensure users don't try to put in negative values for say price, quantity, etc

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

#Makes sure that the user is logged in before they can access sensitive apis such as accounts and carts

def login_required(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        if session.get('loggedin') != 'True' or not session.get('id'):
            abort(401, 'Please log in.')
        return func(*args, **kwargs)
    return wrapped
