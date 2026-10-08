"""Session authentication and single-use password recovery."""
import hashlib
import hmac
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from flask import Blueprint, abort, current_app, jsonify, session
from email_validator import validate_email, EmailNotValidError
from werkzeug.security import generate_password_hash, check_password_hash
from .db import query, execute, transaction
from .validation import body, text, login_required

bp = Blueprint('accounts', __name__)
# Makes missing-user login perform an expensive hash check too.
DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(32))


def password_matches(stored, supplied):
    if stored.startswith(('scrypt:', 'pbkdf2:')):
        return check_password_hash(stored, supplied)
    # One-time compatibility with the old str(sha256(...).digest()) format.
    legacy = str(hashlib.sha256(supplied.encode()).digest())
    return hmac.compare_digest(stored, legacy)


@bp.post('/signup')
def signup():
    data = body()
    username = text(data, 'username', 4)
    password = text(data, 'passwd', 8)
    if any(char.isspace() for char in username):
        abort(400, 'Username cannot contain spaces.')
    try:
        email = validate_email(text(data, 'email'), check_deliverability=False).normalized
    except EmailNotValidError:
        abort(400, 'Email is not valid.')
    fields = {}
    for name in ['firstname', 'lastname', 'streetaddress', 'city', 'state', 'zipcode']:
        value = data.get(name)
        if value is not None and (not isinstance(value, str) or len(value) > 255):
            abort(400, f'{name} must be a string of at most 255 characters.')
        fields[name] = value or None
    with transaction():
        if query('SELECT id FROM customer WHERE username = %s OR email = %s', (username, email)):
            abort(409, 'Username or email is already registered.')
        execute('''INSERT INTO customer
            (email, firstname, lastname, passwd, streetaddress, username, zipcode, city, state)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (email, fields['firstname'], fields['lastname'], generate_password_hash(password),
             fields['streetaddress'], username, fields['zipcode'], fields['city'], fields['state']))
    return jsonify('Query inserted successfully'), 201


@bp.post('/login')
def login():
    data = body()
    username = text(data, 'username')
    password = text(data, 'passwd', 1)
    with transaction():
        user = query('SELECT id, username, passwd FROM customer WHERE username = %s FOR UPDATE',
                     (username,), one=True)
        if user is None:
            check_password_hash(DUMMY_HASH, password)
            valid = False
        else:
            valid = password_matches(user['passwd'], password)
        session.clear()
        if not valid:
            return jsonify(loggedin='False'), 401
        if not user['passwd'].startswith(('scrypt:', 'pbkdf2:')):
            execute('UPDATE customer SET passwd = %s WHERE id = %s',
                    (generate_password_hash(password), user['id']))
    session.permanent = True
    session.update(loggedin='True', id=str(user['id']), username=user['username'])
    return jsonify(loggedin='True', id=str(user['id']))


@bp.get('/getlogin')
def getlogin():
    if session.get('loggedin') == 'True' and session.get('id'):
        return jsonify(loggedin='True', id=session['id'])
    return jsonify(loggedin='False')


@bp.post('/logout')
def logout():
    session.clear()
    return jsonify(Signout='Successful')


@bp.get('/userdata')
@login_required
def userdata():
    # Deliberately never serialize password hashes or reset codes.
    user = query('''SELECT firstname, lastname, username, email, streetaddress, zipcode,
                    city, state FROM customer WHERE id = %s''', (session['id'],), one=True)
    if user is None:
        abort(404, 'Account not found.')
    return jsonify([user])


@bp.get('/alluserdata')
def alluserdata():
    abort(403, 'Bulk customer export is not available through the storefront API.')


@bp.get('/checkshippingaddress')
@login_required
def shippingaddress():
    user = query('''SELECT city,state,streetaddress,zipcode,email,firstname,lastname
                    FROM customer WHERE id = %s''', (session['id'],), one=True)
    return jsonify(user if user and all(user.values()) else None)


@bp.patch('/updateshippingaddress')
@login_required
def update_shipping():
    data = body()
    allowed = ['city', 'state', 'streetaddress', 'zipcode', 'firstname', 'lastname']
    fields = {name: text(data, name) for name in allowed if name in data}
    if not fields:
        abort(400, 'Supply at least one address field.')
    # Column names come exclusively from the fixed allowlist above.
    assignments = ', '.join(f'{name} = %s' for name in fields)
    with transaction():
        changed = execute(f'UPDATE customer SET {assignments} WHERE id = %s',
                          (*fields.values(), session['id']))
        if not changed:
            abort(404, 'Account not found.')
    return jsonify('Query inserted successfully')


def send_recovery_email(username, code, email):
    config = current_app.config
    sender = config['SENDER_EMAIL']
    if not sender or not config['SENDER_PASSWORD']:
        abort(503, 'Password recovery email is not configured.')
    message = EmailMessage()
    message['From'] = sender
    message['To'] = email
    message['Subject'] = 'Password recovery code'
    message.set_content(f'Hi {username},\n\nYour recovery code is {code}. '
                        'It expires in one hour.\nIf you did not request this, ignore this email.')
    with smtplib.SMTP(config['SMTP_HOST'], config['SMTP_PORT'], timeout=10) as server:
        import ssl
        server.starttls(context=ssl.create_default_context())
        server.login(sender, config['SENDER_PASSWORD'])
        server.send_message(message)


@bp.post('/sendemail')
def sendemail():
    username = text(body(), 'username')
    if not current_app.config['SENDER_EMAIL'] or not current_app.config['SENDER_PASSWORD']:
        abort(503, 'Password recovery email is not configured.')
    session.pop('reset_username', None)
    session.pop('reset_expires', None)
    with transaction():
        user = query('SELECT email FROM customer WHERE username = %s FOR UPDATE', (username,), one=True)
        if user:
            code = f'{secrets.randbelow(1000000):06d}'
            hashed = generate_password_hash(code)
            execute('UPDATE customer SET temporarypasscode = %s, codedate = %s, reset_token_digest = NULL, reset_token_expires = NULL WHERE username = %s',
                    (hashed, datetime.now(timezone.utc), username))
            # Never return the code to the caller. Failure rolls back the code.
            send_recovery_email(username, code, user['email'])
    return jsonify(message='If that account exists, a recovery email has been sent.')


@bp.post('/passwordcode')
def passwordcode():
    data = body()
    username = text(data, 'username')
    code = text(data, 'passwordcode', 6, 6)
    if not code.isascii() or not code.isdigit():
        abort(400, 'passwordcode must be six digits.')
    session.pop('reset_username', None)
    session.pop('reset_expires', None)
    valid = False
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    with transaction():
        user = query('SELECT temporarypasscode, codedate FROM customer WHERE username = %s FOR UPDATE',
                     (username,), one=True)
        if user and user['temporarypasscode'] and user['codedate']:
            issued = user['codedate']
            if isinstance(issued, str):
                issued = datetime.fromisoformat(issued)
            if issued.tzinfo is None:
                issued = issued.replace(tzinfo=timezone.utc)
            valid = (timedelta(0) <= datetime.now(timezone.utc) - issued <= timedelta(hours=1)
                     and check_password_hash(str(user['temporarypasscode']), code))
            if valid:
                execute('''UPDATE customer SET temporarypasscode = NULL, codedate = NULL,
                           reset_token_digest = %s, reset_token_expires = %s WHERE username = %s''',
                        (hashlib.sha256(token.encode()).hexdigest(), expires, username))
    if not valid:
        return jsonify('False'), 400
    # Bind a short-lived reset grant to this signed browser session.
    session['reset_token'] = token
    session['reset_username'] = username
    session['reset_expires'] = (datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()
    return jsonify('True')


@bp.patch('/passwordchange')
def passwordchange():
    data = body()
    username = text(data, 'username')
    password = text(data, 'password', 8)
    if (session.get('reset_username') != username or
            session.get('reset_expires', 0) <= datetime.now(timezone.utc).timestamp()):
        abort(403, 'Verify a recovery code before changing the password.')
    with transaction():
        changed = execute('''UPDATE customer SET passwd = %s, temporarypasscode = NULL,
                             codedate = NULL, reset_token_digest = NULL, reset_token_expires = NULL
                             WHERE username = %s AND reset_token_digest = %s
                             AND reset_token_expires > %s''',
                          (generate_password_hash(password), username,
                           hashlib.sha256(session.get('reset_token', '').encode()).hexdigest(),
                           datetime.now(timezone.utc)))
        if not changed:
            abort(403, 'Recovery grant expired or already used.')
    session.clear()
    return jsonify('Password changed successfully')
