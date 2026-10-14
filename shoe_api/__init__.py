"""Application factory for the shoe store API."""

#This was developed as a way to have a single location for creating the flask app and have it connected to the db, better than scattering security and config logic across every file

import os
from datetime import timedelta
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException
import psycopg2
from .db import close_db


def create_app(config=None):
    app = Flask(__name__)
    #Retrieves all the envs needed for the apis
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY'),
        DATABASE_URL=os.environ.get('DATABASE_URL'),
        FRONTEND_URL=os.environ.get('FRONTEND_URL', 'http://localhost:3000'),
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', 'true').lower() == 'true',
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='None',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
        MAX_CONTENT_LENGTH=32 * 1024,
        RATELIMIT_STORAGE_URI=os.environ.get('RATELIMIT_STORAGE_URI', 'memory://'),
        SMTP_HOST=os.environ.get('SMTP_HOST', 'smtp.gmail.com'),
        SMTP_PORT=int(os.environ.get('SMTP_PORT', '587')),
        SENDER_EMAIL=os.environ.get('SENDER_EMAIL'),
        SENDER_PASSWORD=os.environ.get('SENDER_PASSWORD'),
    )
    if config:
        app.config.update(config)
        
    #Checks to make sure that a secret key was passed in
    if not app.config['SECRET_KEY'] or len(app.config['SECRET_KEY']) < 32:
        raise RuntimeError('Set SECRET_KEY to a random value of at least 32 characters.')
    
    #Retrieves the Frontend urls that are allowed to use these apis, used as a security measure to prevent any website from accessing it
    origins = [s.strip().rstrip('/') for s in app.config['FRONTEND_URL'].split(',') if s.strip()]
    if not origins or '*' in origins or any(not s.startswith(('https://', 'http://')) for s in origins):
        raise RuntimeError('FRONTEND_URL must contain explicit HTTP(S) origins.')
    app.config['ALLOWED_ORIGINS'] = origins
    
    #Sets up the CORS so the apis can be used for cross origin requests
    CORS(app, origins=origins, supports_credentials=True,
         allow_headers=['Content-Type'], methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'])
    
    #Closes the db connection at the end of the request regardless if it succeeded, crashed, hit 404, or threw an exception
    app.teardown_appcontext(close_db)
    
    #Limits the number of requests a user can make to the apis per minute
    limiter = Limiter(get_remote_address, app=app, default_limits=['300 per minute'])
    app.extensions['shoe_rate_limiter'] = limiter

    #Runs before every request that modifies data (POST/PATCH/DELETE) and rejects it unless two conditions hold: 1) the Origin header matches an allowed frontend, and 2) the body is JSON
    @app.before_request
    def check_origin():
        # All mutations require an approved browser origin AND JSON. CORS alone
        # does not prevent cross-site form submissions with session cookies.
        if request.method in {'POST', 'PATCH', 'DELETE'}:
            if request.headers.get('Origin') not in origins:
                return jsonify(message='Origin is not allowed.'), 403
            if not request.is_json:
                return jsonify(message='Send a JSON request body.'), 415

    #Runs after every route has produced a response and adds security headers before sending it back to the client. The cache-control header is skipped for catalog pages since those are safe to cache
    @app.after_request
    def response_headers(response):
        #Stops browsers from guessing content types
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if request.path not in {'/allshoes', '/allmainimages', '/allshoedata',
                                '/allshoecolors', '/shoeimages', '/shoedata',
                                '/shoebrand', '/allsizes', '/differentshoecolors'}:
            response.headers['Cache-Control'] = 'no-store'
        return response

    #Handles any Flask abort() call (400, 401, 403, 404, etc.) and returns the error message as JSON
    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(message=error.description), error.code

    #Handles data errors that conflict with what we currently have
    @app.errorhandler(psycopg2.IntegrityError)
    def conflict(error):
        return jsonify(message='The requested change conflicts with existing data.'), 409

    #Catch-all for any psycopg2 database error (timeouts, bad queries, dropped connections, etc.) and only logs the real error message server-side instead of returning it to the client, so SQL and credentials never leak
    @app.errorhandler(psycopg2.Error)
    def database_error(error):
        app.logger.error('Database request failed (%s)', type(error).__name__)
        return jsonify(message='Database temporarily unavailable.'), 503

    #Catches any unexpected error that wasn't caught by the handlers above, logs it server-side, and returns a generic 500 so stack traces never leak to the client
    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.error('Request failed (%s)', type(error).__name__)
        return jsonify(message='Internal server error.'), 500

    #Pulls in the three blueprints defined in accounts/catalog/carts and plugs their routes into the app, blueprints group apis by category so signup and login live in accounts
    from . import accounts, catalog, carts
    app.register_blueprint(accounts.bp)
    app.register_blueprint(catalog.bp)
    app.register_blueprint(carts.bp)
    
    #Used to put a limit to the number of requests made to each api, 10 requests per minute, 60 per hour, these requests are the most likely ones to be hit by attackers
    for endpoint in ['accounts.login', 'accounts.signup', 'accounts.sendemail',
                     'accounts.passwordcode', 'accounts.passwordchange']:
        app.view_functions[endpoint] = limiter.limit('10 per minute; 60 per hour')(app.view_functions[endpoint])
    return app
