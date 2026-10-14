"""Route regression tests against an isolated SQLite DB-API adapter.

PostgreSQL row-lock/concurrency semantics require separate staging validation.
"""
import sqlite3
from decimal import Decimal
import psycopg2
import pytest
from werkzeug.security import generate_password_hash
from shoe_api import create_app

SCHEMA = '''
CREATE TABLE customer(id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE,
    passwd TEXT, firstname TEXT, lastname TEXT, streetaddress TEXT, zipcode TEXT,
    city TEXT, state TEXT, temporarypasscode TEXT, codedate TIMESTAMP,
    reset_token_digest TEXT, reset_token_expires TIMESTAMP, orderid INTEGER);
CREATE TABLE cart(cart_id INTEGER PRIMARY KEY, customer_id INTEGER UNIQUE);
CREATE TABLE cartitems(cart_item_id INTEGER PRIMARY KEY, cart_id INTEGER,
    shoe_id INTEGER, size_id INTEGER, quantity INTEGER CHECK(quantity BETWEEN 1 AND 99),
    UNIQUE(shoe_id,cart_id,size_id));
CREATE TABLE sizes(size_id INTEGER PRIMARY KEY, shoe_id INTEGER, size TEXT,
    in_stock INTEGER CHECK(in_stock >= 0));
CREATE TABLE orders(order_id INTEGER PRIMARY KEY, order_date DATE, total NUMERIC);
CREATE TABLE brand(brand_id INTEGER PRIMARY KEY,brand_name TEXT);
CREATE TABLE manufacture(manufacture_id INTEGER PRIMARY KEY,manufacture_name TEXT);
CREATE TABLE shoe(id INTEGER PRIMARY KEY,brand_id INTEGER,manufacture_id INTEGER,
    price NUMERIC,shoe_name TEXT,sex TEXT,color TEXT,color_order INTEGER,descript TEXT);
CREATE TABLE image(image_id INTEGER PRIMARY KEY,shoe_id INTEGER,brand_id INTEGER,
    image_url TEXT,main_image INTEGER);
CREATE UNIQUE INDEX image_one_main_per_shoe ON image(shoe_id) WHERE main_image = 1;
'''


class Cursor:
    def __init__(self, conn):
        self.inner = conn.cursor()
    def execute(self, sql, params=()):
        sql = sql.replace('%s', '?').replace(' FOR UPDATE', '')
        params = tuple(str(x) if isinstance(x, Decimal) else x.isoformat() if hasattr(x, 'isoformat') else x for x in params)
        try:
            return self.inner.execute(sql, params)
        except sqlite3.IntegrityError as error:
            raise psycopg2.IntegrityError('test constraint conflict') from error
    def __getattr__(self, name):
        return getattr(self.inner, name)


class Connection:
    def __init__(self, path):
        self.inner = sqlite3.connect(path)
        self.closed = False
    def cursor(self):
        return Cursor(self.inner)
    def commit(self):
        self.inner.commit()
    def rollback(self):
        self.inner.rollback()
    def close(self):
        self.inner.close()
        self.closed = True


@pytest.fixture
def app(tmp_path):
    path = tmp_path / 'test.db'
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.close()
    factory = lambda: Connection(path)
    opened = []
    def connect():
        conn = factory()
        opened.append(conn)
        return conn
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret-' * 5,
                      'DB_CONNECT': connect, 'FRONTEND_URL': 'https://store.example',
                      'SESSION_COOKIE_SECURE': False, 'RATELIMIT_ENABLED': False,
                      'SENDER_EMAIL': 'sender@example.com', 'SENDER_PASSWORD': 'test-only'})
    app.opened = opened
    app.db_factory = factory
    conn = factory()
    cur = conn.cursor()
    for uid, name in [(1, 'alice'), (2, 'bobby')]:
        cur.execute('INSERT INTO customer(id,username,email,passwd) VALUES (%s,%s,%s,%s)',
                    (uid, name, name + '@example.com', generate_password_hash('password123')))
    cur.execute("INSERT INTO brand VALUES (1,'Nike')")
    cur.execute("INSERT INTO manufacture VALUES (1,'Nike')")
    cur.execute("INSERT INTO shoe VALUES (1,1,1,135.10,'Shadow','Woman','blue',1,'Test shoe')")
    cur.execute("INSERT INTO shoe VALUES (2,1,1,100,'Other','Man','black',2,'Other shoe')")
    cur.execute("INSERT INTO sizes VALUES (1,1,'8',5)")
    cur.execute("INSERT INTO sizes VALUES (2,2,'8',5)")
    cur.execute("INSERT INTO image VALUES (1,1,1,'https://example.com/shoe.jpg',1)")
    cur.execute("INSERT INTO cart VALUES (1,1)")
    cur.execute("INSERT INTO cart VALUES (2,2)")
    cur.execute("INSERT INTO cartitems VALUES (1,1,1,1,2)")
    cur.execute("INSERT INTO cartitems VALUES (2,2,1,1,1)")
    conn.commit()
    cur.close()
    conn.close()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def authenticated(client):
    with client.session_transaction() as session:
        session.update(loggedin='True', id='1', username='alice')
    return client


def mutate(client, method, path, data=None, origin='https://store.example'):
    return client.open(path, method=method, json={} if data is None else data,
                       headers={'Origin': origin})


def read_db(app, sql, params=()):
    conn = app.db_factory()
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()
