"""One connection per request, always rolled back and closed on exit."""
from contextlib import contextmanager
from flask import current_app, g
import psycopg2


def get_db():
    if 'db' not in g:
        factory = current_app.config.get('DB_CONNECT')
        if factory:
            g.db = factory()
        else:
            url = current_app.config['DATABASE_URL']
            if not url:
                raise psycopg2.OperationalError('DATABASE_URL is not configured')
            g.db = psycopg2.connect(url, connect_timeout=5)
    return g.db


def close_db(error=None):
    conn = g.pop('db', None)
    if conn is not None:
        try:
            conn.rollback()
        finally:
            conn.close()


@contextmanager
def cursor():
    cur = get_db().cursor()
    try:
        yield cur
    finally:
        cur.close()


def rows(cur):
    columns = [column[0] for column in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def query(sql, params=(), one=False):
    with cursor() as cur:
        cur.execute(sql, params)
        result = rows(cur)
    return (result[0] if result else None) if one else result


def execute(sql, params=()):
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


@contextmanager
def transaction():
    conn = get_db()
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise
