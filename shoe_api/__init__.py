"""Application factory for the shoe store API."""
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
    if not app.config['SECRET_KEY'] or len(app.config['SECRET_KEY']) < 32:
        raise RuntimeError('Set SECRET_KEY to a random value of at least 32 characters.')
    origins = [s.strip().rstrip('/') for s in app.config['FRONTEND_URL'].split(',') if s.strip()]
    if not origins or '*' in origins or any(not s.startswith(('https://', 'http://')) for s in origins):
        raise RuntimeError('FRONTEND_URL must contain explicit HTTP(S) origins.')
    app.config['ALLOWED_ORIGINS'] = origins
    CORS(app, origins=origins, supports_credentials=True,
         allow_headers=['Content-Type'], methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'])
    app.teardown_appcontext(close_db)
    limiter = Limiter(get_remote_address, app=app, default_limits=['300 per minute'])
    app.extensions['shoe_rate_limiter'] = limiter

    @app.before_request
    def check_origin():
        # All mutations require an approved browser origin AND JSON. CORS alone
        # does not prevent cross-site form submissions with session cookies.
        if request.method in {'POST', 'PATCH', 'DELETE'}:
            if request.headers.get('Origin') not in origins:
                return jsonify(message='Origin is not allowed.'), 403
            if not request.is_json:
                return jsonify(message='Send a JSON request body.'), 415

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if request.path not in {'/allshoes', '/allmainimages', '/allshoedata',
                                '/allshoecolors', '/shoeimages', '/shoedata',
                                '/shoebrand', '/allsizes', '/differentshoecolors'}:
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(message=error.description), error.code

    @app.errorhandler(psycopg2.IntegrityError)
    def conflict(error):
        return jsonify(message='The requested change conflicts with existing data.'), 409

    @app.errorhandler(psycopg2.Error)
    def database_error(error):
        app.logger.error('Database request failed (%s)', type(error).__name__)
        return jsonify(message='Database temporarily unavailable.'), 503

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.error('Request failed (%s)', type(error).__name__)
        return jsonify(message='Internal server error.'), 500

    from . import accounts, catalog, carts
    app.register_blueprint(accounts.bp)
    app.register_blueprint(catalog.bp)
    app.register_blueprint(carts.bp)
    for endpoint in ['accounts.login', 'accounts.signup', 'accounts.sendemail',
                     'accounts.passwordcode', 'accounts.passwordchange']:
        app.view_functions[endpoint] = limiter.limit('10 per minute; 60 per hour')(app.view_functions[endpoint])
    return app
