#The purpose of this file is to have one place where we can make a connection to the db without having to open it for every single API route and remembering to close it, thus preventing conneciton leaks. It also makes cleanup easier

"""One connection per request, always rolled back and closed on exit."""
from contextlib import contextmanager
from flask import current_app, g
import psycopg2

#Opens a connection to the db once per request, caches it on Flask's g object, and reuses that same connection for every query in the request instead of opening a new one each time

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

#Automatically closes the connection after the request is finished, it also rolls back any uncommitted work so nothing half-finished gets saved
def close_db(error=None):
    conn = g.pop('db', None)
    if conn is not None:
        try:
            conn.rollback()
        finally:
            conn.close()


#Hands out a cursor and guarantees it gets closed afterward, even if the query raises an error
@contextmanager
def cursor():
    cur = get_db().cursor()
    try:
        yield cur
    finally:
        cur.close()

#Converts the cursor's tuple results into a list of dictionaries, using the column names as keys so the results are easier to work with and jsonify
def rows(cur):
    columns = [column[0] for column in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]

#Used for SELECT queries, pass in the sql along with its params. Set one=True to get back a single row instead of a list when you only expect one match
def query(sql, params=(), one=False):
    with cursor() as cur:
        cur.execute(sql, params)
        result = rows(cur)
    return (result[0] if result else None) if one else result


#Used for INSERT/UPDATE/DELETE queries. Returns the number of rows that were affected so the caller can check whether the statement actually changed anything
def execute(sql, params=()):
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount

#Groups multiple queries into a single transaction. If everything inside the with block runs cleanly it all commits together, but if any query throws an exception everything rolls back so you can't end up with half-finished writes (like stock being decremented without an order actually being created)
@contextmanager
def transaction():
    conn = get_db()
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise
