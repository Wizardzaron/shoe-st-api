from datetime import datetime, timedelta, timezone
import hashlib
import psycopg2
import pytest
from werkzeug.security import check_password_hash, generate_password_hash
from shoe_api import accounts, create_app
from conftest import mutate, read_db


def write_db(app, sql, params=()):
    conn = app.db_factory()
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        conn.commit()
    finally:
        cur.close()
        conn.close()


@pytest.mark.parametrize('method,path', [('GET','/cartitems'), ('GET','/userdata'),
    ('POST','/cartitem'), ('PATCH','/newquantity'), ('POST','/ordercreate')])
def test_authentication_required(client, method, path):
    response = mutate(client, method, path) if method != 'GET' else client.get(path)
    assert response.status_code == 401


@pytest.mark.parametrize('method,path,data', [
    ('DELETE','/cartitemremoved',{'cart_item_id':2}),
    ('PATCH','/newquantity',{'cart_item_id':2,'newQuantity':3}),
    ('PATCH','/changeshoesize',{'cart_item_id':2,'id':1})])
def test_other_customer_items_are_inaccessible(app, authenticated, method, path, data):
    assert mutate(authenticated, method, path, data).status_code == 404
    assert read_db(app, 'SELECT quantity FROM cartitems WHERE cart_item_id = 2') == [(1,)]


def test_clear_cart_ignores_supplied_customer_id(app, authenticated):
    assert mutate(authenticated, 'DELETE', '/cartdataremoved', {'customer_id':2}).status_code == 200
    assert read_db(app, 'SELECT cart_item_id FROM cartitems') == [(2,)]


@pytest.mark.parametrize('quantity', [-1, 0, True, 1.5, 'abc', 100])
def test_invalid_quantities(authenticated, quantity):
    assert mutate(authenticated,'PATCH','/newquantity',
                  {'cart_item_id':1,'newQuantity':quantity}).status_code == 400


def test_size_must_belong_to_shoe(app, authenticated):
    assert mutate(authenticated,'PATCH','/changeshoesize',{'cart_item_id':1,'id':2}).status_code == 409
    assert read_db(app, 'SELECT size_id FROM cartitems WHERE cart_item_id = 1') == [(1,)]


def test_add_item_increments_and_checks_stock(app, authenticated):
    assert mutate(authenticated,'POST','/cartitem',{'shoe_id':1,'size_id':1}).status_code == 201
    assert read_db(app,'SELECT quantity FROM cartitems WHERE cart_item_id = 1') == [(3,)]
    assert mutate(authenticated,'POST','/cartitem',{'shoe_id':1,'size_id':2}).status_code == 409


def test_cart_shape_and_exact_total(authenticated):
    response = authenticated.get('/cartitems')
    assert response.status_code == 200
    items, subtotal = response.json
    assert len(items) == 1 and items[0]['cart_item_id'] == 1
    assert str(subtotal['subTotal']) == '270.20'
    assert authenticated.get('/totalcost?prices=0.01&quantity=1').text == '270.20'


def test_checkout_ignores_client_price_and_cart(app, authenticated):
    response = mutate(authenticated,'POST','/ordercreate',{'total':0.01,'cart_id':2})
    assert response.status_code == 201
    assert float(read_db(app,'SELECT total FROM orders')[0][0]) == 270.20
    assert read_db(app,'SELECT in_stock FROM sizes WHERE size_id = 1') == [(3,)]
    assert read_db(app,'SELECT cart_item_id FROM cartitems') == [(2,)]
    assert mutate(authenticated,'POST','/ordercreate').status_code == 409


def test_checkout_out_of_stock_rolls_back(app, authenticated):
    write_db(app, 'UPDATE sizes SET in_stock = 1 WHERE size_id = 1')
    assert mutate(authenticated,'POST','/ordercreate').status_code == 409
    assert read_db(app,'SELECT order_id FROM orders') == []
    assert read_db(app,'SELECT quantity FROM cartitems WHERE cart_item_id = 1') == [(2,)]


def test_checkout_failure_after_stock_change_rolls_back(app, authenticated, monkeypatch):
    from shoe_api import carts
    original = carts.query
    def fail(sql, *args, **kwargs):
        if sql.startswith('INSERT INTO orders'):
            raise psycopg2.OperationalError('SECRET database connection details')
        return original(sql, *args, **kwargs)
    monkeypatch.setattr(carts, 'query', fail)
    response = mutate(authenticated,'POST','/ordercreate')
    assert response.status_code == 503
    assert 'SECRET' not in response.text
    assert read_db(app,'SELECT in_stock FROM sizes WHERE size_id = 1') == [(5,)]
    assert read_db(app,'SELECT quantity FROM cartitems WHERE cart_item_id = 1') == [(2,)]


def test_origin_and_json_enforced(client):
    assert mutate(client,'POST','/login',{},origin='https://evil.example').status_code == 403
    assert client.post('/login',data={'username':'alice'},headers={'Origin':'https://store.example'}).status_code == 415
    assert mutate(client,'POST','/login',[],origin='https://store.example').status_code == 400
    assert client.get('/login?username=alice&passwd=password123').status_code == 405


def test_cors_does_not_allow_unknown_origins(client):
    response = client.get('/getlogin',headers={'Origin':'https://evil.example'})
    assert 'Access-Control-Allow-Origin' not in response.headers
    allowed = client.get('/getlogin',headers={'Origin':'https://store.example'})
    assert allowed.headers['Access-Control-Allow-Origin'] == 'https://store.example'


def test_login_failed_attempt_clears_existing_identity(authenticated):
    assert mutate(authenticated,'POST','/login',{'username':'alice','passwd':'wrong'}).status_code == 401
    assert authenticated.get('/cartitems').status_code == 401


def test_legacy_password_upgrades_without_plaintext(app, client, capsys):
    legacy = str(hashlib.sha256(b'password123').digest())
    write_db(app,'UPDATE customer SET passwd = %s WHERE id = 1', (legacy,))
    assert mutate(client,'POST','/login',{'username':'alice','passwd':'password123'}).status_code == 200
    stored = read_db(app,'SELECT passwd FROM customer WHERE id = 1')[0][0]
    assert stored.startswith('scrypt:') and check_password_hash(stored,'password123')
    assert 'password123' not in capsys.readouterr().out


def test_user_data_never_contains_password(authenticated):
    data = authenticated.get('/userdata').json
    assert 'passwd' not in data[0] and 'temporarypasscode' not in data[0]
    assert authenticated.get('/alluserdata').status_code == 403


def test_password_cannot_be_changed_without_recovery(app, client):
    before = read_db(app,'SELECT passwd FROM customer WHERE id = 1')
    assert mutate(client,'PATCH','/passwordchange',{'username':'alice','password':'hacked123'}).status_code == 403
    assert read_db(app,'SELECT passwd FROM customer WHERE id = 1') == before


def test_recovery_code_is_not_returned_and_is_hashed(app, client, monkeypatch):
    sent = []
    monkeypatch.setattr(accounts,'send_recovery_email',lambda username,code,email:sent.append(code))
    response = mutate(client,'POST','/sendemail',{'username':'alice'})
    missing = mutate(client,'POST','/sendemail',{'username':'unknown'})
    assert response.json == missing.json and 'code' not in response.json
    stored = read_db(app,'SELECT temporarypasscode FROM customer WHERE id = 1')[0][0]
    assert stored != sent[0] and check_password_hash(stored,sent[0])


def test_recovery_is_single_use_and_bound_to_browser(app, client, monkeypatch):
    sent = []
    monkeypatch.setattr(accounts,'send_recovery_email',lambda username,code,email:sent.append(code))
    mutate(client,'POST','/sendemail',{'username':'alice'})
    assert mutate(client,'POST','/passwordcode',{'username':'alice','passwordcode':sent[0]}).json == 'True'
    other = app.test_client()
    assert mutate(other,'POST','/passwordcode',{'username':'alice','passwordcode':sent[0]}).status_code == 400
    assert mutate(other,'PATCH','/passwordchange',{'username':'alice','password':'newpassword123'}).status_code == 403
    # Even a replayed pre-reset signed cookie cannot reuse the consumed DB grant.
    old_cookie = client.get_cookie('session').value
    assert mutate(client,'PATCH','/passwordchange',{'username':'alice','password':'newpassword123'}).status_code == 200
    other.set_cookie('session',old_cookie)
    assert mutate(other,'PATCH','/passwordchange',{'username':'alice','password':'anotherpassword'}).status_code == 403
    assert mutate(client,'POST','/login',{'username':'alice','passwd':'newpassword123'}).status_code == 200


def test_expired_code_is_rejected(app, client):
    write_db(app,'UPDATE customer SET temporarypasscode = %s,codedate = %s WHERE id = 1',
             (generate_password_hash('123456'),datetime.now(timezone.utc)-timedelta(hours=2)))
    assert mutate(client,'POST','/passwordcode',{'username':'alice','passwordcode':'123456'}).status_code == 400


def test_missing_shoe_and_invalid_ids(client):
    assert client.get('/shoedata?id=999').status_code == 404
    assert client.get('/shoedata?id=abc').status_code == 400
    assert client.get('/shoedata?id=1').json['shoe_name'] == 'Shadow'


@pytest.mark.parametrize('path', ['/allshoes','/allmainimages','/allshoedata','/allshoecolors',
    '/shoeimages','/allsizes?id=1','/differentshoecolors?id=1','/shoebrand?manufacture_id=1'])
def test_catalog_routes(client,path):
    assert client.get(path).status_code == 200


def test_database_connections_close_on_success_and_validation_failure(app, authenticated):
    authenticated.get('/shoedata?id=1')
    mutate(authenticated,'POST','/cartitem',{'shoe_id':1,'size_id':2})
    assert app.opened and all(conn.closed for conn in app.opened)


def test_secret_must_be_configured():
    with pytest.raises(RuntimeError):
        create_app({'SECRET_KEY':None})


def test_signup_and_logout(client):
    response = mutate(client,'POST','/signup',{'username':'charlie','email':'charlie@example.com','passwd':'password123'})
    assert response.status_code == 201
    assert mutate(client,'POST','/signup',{'username':'charlie','email':'different@example.com','passwd':'password123'}).status_code == 409
    assert mutate(client,'POST','/login',{'username':'charlie','passwd':'password123'}).status_code == 200
    assert mutate(client,'POST','/logout').status_code == 200
    assert client.get('/getlogin').json == {'loggedin':'False'}


def test_auth_routes_are_rate_limited():
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret-' * 5,
                      'FRONTEND_URL': 'https://store.example',
                      'RATELIMIT_STORAGE_URI': 'memory://'})
    client = app.test_client()
    responses = [mutate(client,'POST','/login',{}) for _ in range(11)]
    assert responses[-1].status_code == 429


def test_preflight_allows_json_from_frontend(client):
    response = client.options('/login',headers={'Origin':'https://store.example',
                              'Access-Control-Request-Method':'POST',
                              'Access-Control-Request-Headers':'Content-Type'})
    assert response.status_code == 200
    assert response.headers['Access-Control-Allow-Credentials'] == 'true'


def test_database_failure_closes_connection(client, app, monkeypatch):
    from shoe_api import catalog
    def broken(sql,*args,**kwargs):
        from shoe_api.db import get_db
        get_db()
        raise psycopg2.OperationalError('private details')
    monkeypatch.setattr(catalog,'query',broken)
    response = client.get('/allshoes')
    assert response.status_code == 503 and 'private details' not in response.text
    assert all(conn.closed for conn in app.opened)
