import psycopg2
import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session, abort, make_response, current_app, jsonify
from datetime import date, datetime, timedelta
from flask import send_from_directory
from functools import wraps
from email_validator import validate_email, EmailNotValidError
import sys
from flask_cors import CORS

import jwt
import logging

app = Flask(__name__)

# supports_credentials allows us to use  include the Access-Control-Allow-Credentials header in the response. thus letting us to send cookies(thus allowing us to properly use sessions) or http authentication
CORS(app, supports_credentials=True)

app.config['SECRET_KEY'] = 'Sa_sa'
# need this for the server side so the cookies containing the id for sessions dont get blocked
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True

app.permanent_session_lifetime = timedelta(minutes=30)

conn = None


def connect_to_database():

    global conn

    # conn = psycopg2.connect(
    #     host=os.environ.get('DB_HOST'),
    #     port=os.environ.get('DB_PORT'),
    #     dbname=os.environ.get('DB_NAME'),
    #     user=os.environ.get('DB_USER'),
    #     password=os.environ.get('DB_PASS'),
    #     keepalives_idle=3000
    # )
    conn = sqlite3.connect("shoe.db", check_same_thread=False)

def fetchObjectFromCursorAll(cursor):
            
    tuple = cursor.fetchall()
    print(tuple)
    # print("description",cursor.description)
    print(len(tuple))

    obs = []
    for i in range(len(tuple)):
        obj = dict()
        for element in range(len(tuple[i])):
            print(f"The element at index {element} is {tuple[i][element]}")
            obj[cursor.description[element][0]] = tuple[i][element]
        obs.append(obj)
    return obs


def fetchObjectFromCursor(cursor):
            
    tuple = cursor.fetchone()
    print(tuple)
    # print("description",cursor.description)

    obj = dict()
    for i in range(len(tuple)):
        print(f"The element at index {i} is {tuple[i]}")
        obj[cursor.description[i][0]] = tuple[i]

    return obj

@app.route('/connect', methods=['GET'])
def check_connection():
    global conn
    if not conn or conn is None:
        connect_to_database()
    connection = conn.closed
    if (connection != 0):
        return jsonify({"message": "No connection"}), 503

    else:
        return jsonify({"message": "Connection is established"}), 200


# @app.route('/updateshoe', methods=['PATCH'])
# def shoedata_update():
#     global conn
#     #These 4 lines of code will ensure that the connection is always established, even if it's lost
#     if not conn or conn.closed:
#         connect_to_database()
#         if conn.closed:
#             return jsonify({"message": "No connection"}), 503

#     cur = conn.cursor()

#     itemid = request.form.get('itemid')
#     images = request.form.get('images')

#     try:
#         updateOldShoe = """UPDATE shoes SET images = %s WHERE item_id = %s"""
#         cur.execute(updateOldShoe, [itemid, images])
#         conn.commit()

#     except Exception as err:

#         msg = 'Query Failed: %s\nError: %s' % (updateOldShoe, str(err))
#         #used to reset connection after bad query transaction
#         conn.rollback()
#         return jsonify ( msg)

#     finally:
#         cur.close()

#     return jsonify('shoe updated successfully')

# @app.route('/addshoe', methods=['POST'])
# def shoedata_post():
#     global conn
#     if not conn or conn.closed:
#         connect_to_database()
#         if conn.closed:
#             return jsonify({"message": "No connection"}), 503

#     cur = conn.cursor()

#     itemid = request.form.get('itemid')
#     category = request.form.get('category')
#     brand = request.form.get('brand')
#     color = request.form.get('color')
#     gender = request.form.get('gender')
#     shoesize = request.form.get('shoesize')
#     images = request.form.get('images')
#     descript = request.form.get('descript')
#     price = request.form.get('price')
#     names = request.form.get('names')

#     try:

#         insertNewShoe = """INSERT INTO shoes (names, item_id, category, brand, color, gender, shoesize, price ,images, descript) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
#         cur.execute(insertNewShoe, [names, itemid, category, brand, color, gender, shoesize, price ,images, descript])
#         conn.commit()

#     except Exception as err:

#         msg = 'Query Failed: %s\nError: %s' % (insertNewShoe, str(err))
#         #used to reset connection after bad query transaction
#         conn.rollback()
#         return jsonify ( msg)

#     finally:
#         cur.close()

#     return jsonify('shoe created successfully')

@app.route('/brandimages', methods=['GET'])
def brandimages_get():

    global conn
    if not conn or conn is None:
        connect_to_database()
        if conn is None:
            return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()
    rows = []
    brand_id = request.args.get('brand_id')

    try:

        getBrand = '''SELECT DISTINCT i.image_url FROM image as i, shoe as sd WHERE i.main_image = 1 AND sd.brand_id = ?'''
        cur.execute(getBrand,[brand_id])
        brand = cur.fetchall()
        print(brand)
        
        for row in brand:
            rows.append({"image_url": row[0]})

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getBrand, str(e))
        # used to reset connection after bad query transaction
        # conn.rollback()
        return jsonify(msg)

    msg = make_response(jsonify(rows))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'

    return msg


@app.route('/shoeimages', methods=['GET'])
def shoeimages_get():

    # psycopg2 has the .closed attribute but not sqlite3 you need to use None in order to check for a closed connection
    global conn
    if not conn or conn is None:
        connect_to_database()
        if conn is None:
            return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()
    rows = []

    try:

        getImage = '''SELECT shoe_id, image_id, image_url FROM image'''
        cur.execute(getImage)
        images = cur.fetchall()
        print(images)
        columns = ('shoe_id', 'image_id', 'image_url')

        msg = jsonify('Query inserted successfully')
        msg.headers['Access-Control-Allow-Methods'] = 'GET'
        msg.headers['Access-Control-Allow-Credentials'] = 'true'
        msg.headers['Access-Control-Allow-Origin'] = 'https://shoe-st.vercel.app/'

        # creating dictionary
        for row in images:
            print(f"trying to serve {row}", file=sys.stderr)
            rows.append({columns[i]: row[i] for i, _ in enumerate(columns)})
            print(f"trying to serve {rows[-1]}", file=sys.stderr)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getImage, str(e))
        # used to reset connection after bad query transaction
        # conn.rollback()
        return jsonify(msg)

    return rows


@app.route('/allmainimages', methods=['GET'])
def mainimages_get():

    global conn
    if not conn or conn is None:
        connect_to_database()
        if conn is None:
            return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()
    rows = []

    try:

        # this a join
        getImage = '''
        SELECT i.shoe_id, i.image_id, i.image_url, sd.shoe_name, sd.descript, bd.brand_name , bd.brand_id
        FROM image AS i, shoe AS sd, brand AS bd 
        WHERE i.main_image = 1 AND i.shoe_id = sd.id AND sd.brand_id = bd.brand_id'''

        cur.execute(getImage)
        images = cur.fetchall()
        print(images)

        # creating dictionary
        for row in images:
            # print(f"trying to serve {row}", file=sys.stderr)
            # rows.append({columns[i]: row[i] for i, _ in enumerate(columns)})
            # print(f"trying to serve {rows[-1]}", file=sys.stderr)
            rows.append({"shoe_id": row[0], "image_id": row[1], "image_url": row[2],
                        "shoe_name": row[3], "descript": row[4], "brand_name": row[5], "brand_id": row[6]})

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getImage, str(e))
        # used to reset connection after bad query transaction
        # conn.rollback()
        return jsonify(msg)

    msg = make_response(jsonify(rows))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'

    return msg


@app.route('/differentshoecolors', methods=['GET'])
def differentshoecolors_get():

    global conn
    if not conn or conn is None:
        connect_to_database()
        if conn is None:
            return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()
    rows = []
    try:

        shoe_id = request.args.get('id')
        print(shoe_id)
        getInfo = '''SELECT 
        i.image_id,
        i.image_url,
        b.brand_name,
        i.shoe_id, 
        sd.shoe_name
        FROM 
                shoe AS sd, 
                image AS i, 
                brand AS b
        WHERE 
                sd.id = ? AND 
                sd.id = i.shoe_id AND 
                i.main_image = true AND 
                b.brand_id = sd.brand_id'''

        cur.execute(getInfo, [shoe_id])

        # creating dictionary

        # def result_rows(cursor):
        #     columns = [desc[0] for desc in cursor.description]
        #     rows = []
        #     for row in cursor.fetchall():
        #         summary = dict(zip(columns, row))
        #         rows.append(summary)
        #     return rows

        columns = [desc[0] for desc in cur.description]
        rows = []
        for row in cur.fetchall():
            summary = dict(zip(columns, row))
            rows.append(summary)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getInfo, str(e))
        return jsonify(msg)

    msg = make_response(jsonify(rows))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'

    return rows


@app.route('/shoesizes', methods=['GET'])
def allshoesizes_get():

    global conn
    if not conn or conn is None:
        connect_to_database()
        if conn is None:
            return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()
    rows = []

    try:
        id = request.args.get('id')
        getSizes = '''SELECT size, in_stock FROM sizes WHERE shoe_id = ?'''
        cur.execute(getSizes, [id])
        info = cur.fetchall()
        print(info)
        columns = ('size', 'in_stock')

        # creating dictionary
        for row in info:
            print(f"trying to serve {row}", file=sys.stderr)
            rows.append({columns[i]: row[i] for i, _ in enumerate(columns)})
            print(f"trying to serve {rows[-1]}", file=sys.stderr)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getSizes, str(e))
        # used to reset connection after bad query transaction
        # conn.rollback()
        return jsonify(msg)

    msg = make_response(jsonify(rows))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'

    return msg


@app.route('/allshoedata', methods=['GET'])
def allshoedata_get():
    global conn
    if not conn or conn is None:
        connect_to_database()
        if conn is None:
            return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()
    rows = []

    try:

        getData = '''SELECT sd.id, sd.color, sd.sex, sd.price, sd.descript, sd.shoe_name, b.brand_id,b.brand_name
        FROM shoe AS sd, brand AS b'''
        cur.execute(getData)
        info = cur.fetchall()
        print(info)
        columns = ('id', 'color', 'sex', 'price', 'descript',
                   'shoe_name', 'brand_id', 'brand_name')

        # creating dictionary
        for row in info:
            print(f"trying to serve {row}", file=sys.stderr)
            rows.append({columns[i]: row[i] for i, _ in enumerate(columns)})
            print(f"trying to serve {rows[-1]}", file=sys.stderr)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getData, str(e))
        # used to reset connection after bad query transaction
        # conn.rollback()
        return jsonify(msg)

    msg = make_response(jsonify(rows))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'

    return rows


@app.route('/shoedata', methods=['GET'])
def shoedata_get():
    global conn
    if not conn or conn is None:
        connect_to_database()
        if conn is None:
            return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()
    try:

        shoe_id = request.args.get('id')
        print(shoe_id)
        getInfo = '''
        SELECT sd.color, sd.sex, sd.price, sd.descript, sd.shoe_name , i.shoe_id, i.image_id, i.image_url, i.main_image, b.brand_name
        FROM shoe AS sd, image AS i, brand AS b
        WHERE sd.id = ? AND sd.id = i.shoe_id AND b.brand_id = sd.brand_id'''

        cur.execute(getInfo,[shoe_id,])
        shoeObj = fetchObjectFromCursor(cur)

        getSizes = '''SELECT size, in_stock FROM sizes WHERE shoe_id = ?'''

        cur.execute(getSizes,[shoe_id,])
        shoeObj["sizes"] = fetchObjectFromCursorAll(cur)

        print(shoeObj)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getSizes, str(e))
        return jsonify(msg)

    msg = make_response(jsonify(shoeObj))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'

    return msg


@app.route('/shoebrand', methods=['GET'])
def shoebrand_get():
    global conn
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()
    rows = []
    try:

        brand = request.args.get('brand')
        # itemId = 'FB7582-001'
        # print(itemId)
        getInfo = '''SELECT names, item_id, price ,images FROM shoes WHERE brand = %s '''
        cur.execute(getInfo, [brand])
        info = cur.fetchall()

        columns = ('names', 'item_id', 'price', 'images')

        # creating dictionary
        for row in info:
            print(f"trying to serve {row}", file=sys.stderr)
            rows.append({columns[i]: row[i] for i, _ in enumerate(columns)})
            print(f"trying to serve {rows[-1]}", file=sys.stderr)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getInfo, str(e))
        return jsonify(msg)

    return rows

# @app.route('/search', methods=['GET'])
# def search():

#     cur = conn.cursor()

#     try:

#         searching = request.args.get('searchValue')


@app.route('/login', methods=['GET', 'POST'])
def login():
    global conn
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()

    try:

        msg = jsonify('Query inserted successfully')
        msg.headers['Access-Control-Allow-Methods'] = 'POST'
        msg.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        msg.headers['Access-Control-Allow-Origin'] = '*'
        msg.headers['Access-Control-Allow-Credentials'] = True

        username = request.form.get('username')
        passwd = request.form.get('passwd')

        # NOTE in sqlite and postgresql you use %s as placeholders instead of ?

        getCountByUsernameAndPassword = '''SELECT count(*) FROM customer WHERE username = %s AND passwd = %s'''
        cur.execute(getCountByUsernameAndPassword, [username, passwd])

        countOfUsernameAndPassword = cur.fetchone()

        if countOfUsernameAndPassword[0] == 0:
            print('setting logged in to False')
            session['loggedin'] = 'False'

            print('about to return False')
            s = str(session['loggedin'])
            t = '{' + f'"loggedin":"{str(s)}"' + '}'

            # resp = make_response("usernotloggedin", 401)
            # used to reset connection after bad query transaction
            conn.rollback()
            return t

        getId = '''SELECT id FROM customer WHERE username = %s AND passwd = %s'''
        cur.execute(getId, [username, passwd])
        id = cur.fetchone()

        # sessions carry data over the website
        session['loggedin'] = 'True'

        session['username'] = username

        # need to do id[0] because even though their is only one id number we are retrieving it's still wrapped in a tuple
        # and needs to be removed
        session['id'] = str(id[0])

        # print("Id: ", id)
        print("session id does exist in session: ", session.get('id'))

        s = str(session['loggedin'])
        t = '{' + f'"loggedin":"{str(s)}"' + '}'
        print(session)
        print(t)
        return t

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getId, str(e))
        conn.rollback()
        return jsonify(msg)


@app.route('/userdata', methods=['GET'])
def userdata_get():
    global conn
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()
    rows = []
    try:
        msg = jsonify('Query inserted successfully')
        msg.headers['Access-Control-Allow-Methods'] = 'GET'
        msg.headers['Access-Control-Allow-Credentials'] = 'true'
        msg.headers['Access-Control-Allow-Origin'] = '*'

        # need to include CORS credentials in order to send session cookie to client
        msg.headers['Access-Control-Allow-Credentials'] = True

        if "id" not in session:
            msg = ({"message": "User could not be found due to id returning none"})
            return jsonify(msg)

        id = session.get('id')
        # id = int(id)
        # id = request.cookies.get('userID')
        print("id + ", id)
        getInfo = '''SELECT firstname, lastname, username, passwd, email, streetaddress, zipcode FROM customer WHERE id = %s'''

        cur.execute(getInfo, (id, ))
        userInfo = cur.fetchall()

        columns = ('firstname', 'lastname', 'username',
                   'passwd', 'email', 'streetaddress', 'zipcode')

        # creating dictionary
        for row in userInfo:
            print(f"trying to serve {row}", file=sys.stderr)
            rows.append({columns[i]: row[i] for i, _ in enumerate(columns)})
            print(f"trying to serve {rows[-1]}", file=sys.stderr)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getInfo, str(e))
        return jsonify(msg)

    return rows


@app.route('/alluserdata', methods=['GET'])
def all_userdata_get():
    global conn
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()

    rows = []
    try:
        # getInfo =  '''SELECT * FROM customer'''
        getInfo = '''SELECT firstname, lastname, username, passwd, email, streetaddress, zipcode, id, mtd, ytd FROM customer'''
        cur.execute(getInfo)
        info = cur.fetchall()

        columns = ('firstname', 'lastname', 'username', 'passwd',
                   'email', 'streetaddress', 'zipcode', 'id', 'mtd', 'ytd')

        # creating dictionary
        for row in info:
            print(f"trying to serve {row}", file=sys.stderr)
            rows.append({columns[i]: row[i] for i, _ in enumerate(columns)})
            print(f"trying to serve {rows[-1]}", file=sys.stderr)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getInfo, str(e))
        return jsonify(msg)

    return rows


@app.route('/ordercreate', methods=['POST'])
def order_post():
    global conn
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()

    brand = request.form.get('brand')
    itemname = request.form.get('itemname')
    price = request.form.get('price')
    quantity = request.form.get('quantity')
    customer_id = request.form.get('customer_id')
    today = date.today()
    dateoforder = today

    try:

        insertNewUser = """INSERT INTO orders (brand, customer_id, dateoforder, itemname, price, quantity) VALUES (%s,%s,%s,%s,%s,%s)"""
        cur.execute(insertNewUser, [brand, customer_id,
                    dateoforder, itemname, price, quantity])
        conn.commit()

    except Exception as err:

        # return render_template('welcome.html', msg = str(err))

        msg = 'Query Failed: %s\nError: %s' % (insertNewUser, str(err))
        conn.rollback()
        return jsonify(msg)
        # print('Query Failed: %s\nError: %s' % (insertNewUser, str(err)))

    finally:
        cur.close()

    return jsonify('order created successfully')

# @app.route('/setcookie', methods=['GET'])
# def setcookie():

#     resp = make_response("loggedin", 200)
#     #Cookies can only handle the conversion of strings into bytes
#     resp.set_cookie('loggedin', "False", path='/', samesite='None', secure=True)

#     return resp

# @app.route('/getcookie', methods=['GET'])
# def getcookie():

#     try:
#         cookie = request.cookies.get('loggedin')
#         print(cookie)
#         if cookie is None:
#             resp = make_response("Cookie is none")
#             return resp
#         #resp = make_response("The cookie is '{cookie}'".format(cookie=cookie), 200)
#         return resp
#     except Exception as e:
#         resp = make_response("The cookie was not set")
#         return  resp


@app.route('/getlogin', methods=['GET'])
def getlogin():

    msg = jsonify('Trying to retrieve session')
    msg.headers['Access-Control-Allow-Credentials'] = 'true'

    if 'loggedin' in session:

        s = str(session['loggedin'])
        t = '{' + f'"loggedin":"{str(s)}"' + '}'
        print(t)
        return t
    else:
        # used to create session loggedin just in case the cookie doesn't exist yet
        print("Session doesn't exist yet")
        session['loggedin'] = 'False'
        s = str(session['loggedin'])
        t = '{' + f'"loggedin":"{str(s)}"' + '}'
        print(t)
        return t


@app.route('/logout', methods=['GET'])
def logout():

    msg = jsonify('Query inserted successfully')
    msg.headers['Access-Control-Allow-Credentials'] = 'true'

    if 'loggedin' in session:

        session.pop('loggedin', None)
        t = '{' + f'"Signout": "Successful"' + '}'
    else:
        t = '{' + f'"Signout": "Failure"' + '}'
    return t


@app.route('/signup', methods=['POST'])
def signup_post():
    global conn
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()

    data = request.json

    firstname = data.get('firstname')
    lastname = data.get('lastname')
    username = data.get('username')
    email = data.get('email')
    zipcode = data.get('zipcode')
    streetaddress = data.get('streetaddress')
    passwd = data.get('passwd')

    # password must be between 4 and 255
    if len(passwd) < 4 or len(passwd) > 255:
        return jsonify("password must be between 4 and 255")

    # username must be between 4 and 255
    if len(username) < 4 or len(username) > 255:
        return jsonify("Username needs to be between 4 and 255 characters long.")

    # check if email is valid

    # another way of doing if else statement

    try:
        # Check that the email address is valid.
        validation = validate_email(email)
        email = validation.email
    except EmailNotValidError as e:
        # Email is not valid.
        # The exception message is human-readable.
        return jsonify('Email not valid: ' + str(e))

    # username cannot include whitespace
    if any(char.isspace() for char in username):
        return jsonify('Username cannot have spaces in it.')

    # email cannot include whitespace
    if any(char.isspace() for char in email):
        return jsonify('Email cannot have spaces in it.')

    # to select all column we will use
    getCountByUsername = '''SELECT COUNT(*) FROM customer WHERE username = %s'''
    cur.execute(getCountByUsername, [username])
    countOfUsername = cur.fetchone()

    if countOfUsername[0] != 0:
        return jsonify('Username already exists.')

    # ready to insert into database
    try:

        insertNewUser = """INSERT INTO customer (email, firstname, lastname, passwd, streetaddress, username, zipcode) VALUES (%s,%s,%s,%s,%s,%s,%s)"""
        cur.execute(insertNewUser, [
                    email, firstname, lastname, passwd, streetaddress, username, zipcode])
        conn.commit()

        msg = jsonify('Query inserted successfully')
        msg.headers['Access-Control-Allow-Methods'] = 'POST'
        msg.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        msg.headers['Access-Control-Allow-Origin'] = 'https://shoe-st.vercel.app/'

    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (insertNewUser, str(err))
        conn.rollback()
        return jsonify(msg)
    finally:
        cur.close()

    return msg


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
