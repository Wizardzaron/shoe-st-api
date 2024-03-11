import psycopg2
import os
from flask import Flask, render_template, request, redirect, url_for, session, abort, make_response ,current_app,jsonify
from datetime import date, datetime, timedelta
from flask import send_from_directory
from functools import wraps
from email_validator import validate_email, EmailNotValidError
import sys
from flask_cors import CORS

import jwt
import logging

app = Flask(__name__)

#supports_credentials allows us to use  include the Access-Control-Allow-Credentials header in the response. thus letting us to send cookies(thus allowing us to properly use sessions) or http authentication
CORS(app, supports_credentials=True)

app.config['SECRET_KEY'] = 'Sa_sa'
app.permanent_session_lifetime = timedelta(minutes=30)

DB_HOST = 'ep-dark-lake-a4cd73x9-pooler.us-east-1.aws.neon.tech'
DB_PORT = '5432'
DB_NAME = 'verceldb'
DB_USER = 'default'
DB_PASS = 'ugJZCc1av6ob'

conn = None

def connect_to_database():

    global conn

    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        keepalives_idle=3000
    )

# DATABASE_URL = os.environ.get('DATABASE_URL')
# conn = psycopg2.connect(DATABASE_URL, sslmode='require')

@app.route('/connect', methods=['GET'])
def check_connection():
    if not conn or conn.closed:
        connect_to_database()
    connection = conn.closed
    if(connection != 0):
        return jsonify({"message": "No connection"}), 503

    else:
        return jsonify({"message": "Connection is established"}), 200


@app.route('/updateshoe', methods=['PATCH'])
def shoedata_update():
    #These 4 lines of code will ensure that the connection is always established, even if it's lost
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()
    
    itemid = request.form.get('itemid')
    images = request.form.get('images')

    try:
        updateOldShoe = """UPDATE shoes SET images = %s WHERE item_id = %s"""
        cur.execute(updateOldShoe, [itemid, images])
        conn.commit()

    except Exception as err:
            
        msg = 'Query Failed: %s\nError: %s' % (updateOldShoe, str(err))
        #used to reset connection after bad query transaction
        conn.rollback()
        return jsonify ( msg)
            
    finally:
        cur.close()

    return jsonify('shoe updated successfully')

@app.route('/addshoe', methods=['POST'])
def shoedata_post():
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503
    
    cur = conn.cursor()

    itemid = request.form.get('itemid')
    category = request.form.get('category')
    brand = request.form.get('brand')
    color = request.form.get('color')
    gender = request.form.get('gender')
    shoesize = request.form.get('shoesize')
    images = request.form.get('images')
    descript = request.form.get('descript')
    price = request.form.get('price')
    names = request.form.get('names')

    try:

        insertNewShoe = """INSERT INTO shoes (names, item_id, category, brand, color, gender, shoesize, price ,images, descript) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        cur.execute(insertNewShoe, [names, itemid, category, brand, color, gender, shoesize, price ,images, descript])
        conn.commit()

    except Exception as err:
        
        msg = 'Query Failed: %s\nError: %s' % (insertNewShoe, str(err))
        #used to reset connection after bad query transaction
        conn.rollback()
        return jsonify ( msg)
        
    finally:
        cur.close()

    return jsonify('shoe created successfully')

@app.route('/shoeimages', methods=['GET'])
def shoeimages():
    global conn
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()
    rows = []

    try:
        getImages = '''SELECT images, item_id, descript, names, brand FROM shoes'''
        cur.execute(getImages)
        info =cur.fetchall()
        print(info)
        columns = ('images','item_id', 'descript', 'names', 'brand')

        msg = jsonify('Query inserted successfully')
        msg.headers['Access-Control-Allow-Methods'] = 'GET'
        msg.headers['Access-Control-Allow-Credentials'] = 'true'
        msg.headers['Access-Control-Allow-Origin'] = 'https://shoe-st.vercel.app/'

        # creating dictionary
        for row in info:
            print(f"trying to serve {row}", file=sys.stderr)
            rows.append({columns[i]: row[i] for i, _ in enumerate(columns)})
            print(f"trying to serve {rows[-1]}", file=sys.stderr)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getImages, str(e))
        #used to reset connection after bad query transaction
        #conn.rollback()
        return jsonify(msg)

    return rows

@app.route('/shoedata', methods=['GET'])
def shoedata_get():
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()
    rows = []
    try:
        
        itemId = request.args.get('item_id')
        #itemId = 'FB7582-001'
        print(itemId)
        getInfo =  '''SELECT names, category, brand, color, gender, shoesize, price ,images, descript FROM shoes WHERE item_id = %s '''
        cur.execute(getInfo, [itemId])
        info = cur.fetchall()

        columns = ('names', 'category', 'brand', 'color', 'gender', 'shoesize','price' ,'images', 'descript')

        msg = jsonify('Query inserted successfully')
        msg.headers['Access-Control-Allow-Methods'] = 'GET'
        msg.headers['Access-Control-Allow-Credentials'] = 'true'
        msg.headers['Access-Control-Allow-Origin'] = 'https://shoe-st.vercel.app/'

        # creating dictionary
        for row in info:
            print(f"trying to serve {row}", file=sys.stderr)
            rows.append({columns[i]: row[i] for i, _ in enumerate(columns)})
            print(f"trying to serve {rows[-1]}", file=sys.stderr)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getInfo, str(e))
        return jsonify(msg)

    return rows

@app.route('/shoebrand', methods=['GET'])
def shoebrand_get():
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()
    rows = []
    try:
        
        brand = request.args.get('brand')
        #itemId = 'FB7582-001'
        #print(itemId)
        getInfo =  '''SELECT names, item_id, price ,images FROM shoes WHERE brand = %s '''
        cur.execute(getInfo, [brand])
        info = cur.fetchall()

        columns = ('names', 'item_id', 'price' ,'images')

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

        username = request.form.get('username')
        passwd = request.form.get('passwd')

        #NOTE in sqlite and postgresql you use %s as placeholders instead of ?

        getCountByUsernameAndPassword = '''SELECT count(*) FROM customer WHERE username = %s AND passwd = %s'''
        cur.execute(getCountByUsernameAndPassword, [username, passwd])

    
            
            #print("Did execute")
            
        countOfUsernameAndPassword = cur.fetchone()

            #print("Did fetchone")

        if countOfUsernameAndPassword[0] == 0:
            print('setting logged in to False')
            #session['loggedin'] = False
            #token = create_token(user_name, session['loggedin'])
            
            #return jsonify(token)
            print('about to return False')
            #s = str(session['loggedin'])
            #t = '{' + f'"loggedin":"{str(s)}"' + '}'
            #print(t)
            resp = make_response("usernotloggedin", 401)
            #used to reset connection after bad query transaction
            conn.rollback()
            return resp    


        getId = '''SELECT id FROM customer WHERE username = %s AND passwd = %s'''
        cur.execute(getId, [username, passwd])
        id = cur.fetchone()

        #session['Authorization'] = token
        # sessions carry data over the website
        #session['loggedin'] = True

        session['username'] = username

        session['id'] = id
            
        print("session id does exist: ", session.get('id'))

        #token = create_token(user_name, session['loggedin'])
        #print("at the end")
        # print(f'at the end -- printing jsonify|{session["loggedin"]}|and more to go')
        # s = str(session['loggedin'])
        # i = session['id']
        # t = '{' + f'"loggedin":"{str(s)}", "id":"{i}"' +'}'
        resp = make_response("userloggedin", 200)
        resp.set_cookie('userID', id, path='/')

        

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getId, str(e))
        conn.rollback()
        return jsonify(msg)

    return resp

@app.route('/userdata', methods=['GET'])
def userdata_get():
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
         
        #id = request.args.get('id')
        id = request.cookies.get('userID')
        print("id + ", id)
        getInfo =  '''SELECT firstname, lastname, username, passwd, email, streetaddress, zipcode FROM customer WHERE id = %s'''

        cur.execute(getInfo,(id, ))
        userInfo = cur.fetchall()

        columns = ('firstname', 'lastname', 'username', 'passwd', 'email', 'streetaddress', 'zipcode')

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
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()

    rows = []
    try:
        #getInfo =  '''SELECT * FROM customer'''
        getInfo =  '''SELECT firstname, lastname, username, passwd, email, streetaddress, zipcode, id, mtd, ytd FROM customer'''
        cur.execute(getInfo)
        info = cur.fetchall()

        columns = ('firstname', 'lastname', 'username', 'passwd', 'email', 'streetaddress', 'zipcode', 'id', 'mtd', 'ytd')

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
        cur.execute(insertNewUser, [brand, customer_id, dateoforder, itemname, price, quantity])
        conn.commit()

    except Exception as err:
        
        #return render_template('welcome.html', msg = str(err))

        msg = 'Query Failed: %s\nError: %s' % (insertNewUser, str(err))
        conn.rollback()
        return jsonify ( msg)
        #print('Query Failed: %s\nError: %s' % (insertNewUser, str(err)))
        
    finally:
        cur.close()

    return jsonify('order created successfully')

@app.route('/signup', methods=['POST'])
def signup_post():
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

	#password must be between 4 and 255
    if len(passwd) < 4 or len(passwd) > 255:
        return jsonify ("password must be between 4 and 255")    
    
    #username must be between 4 and 255 
    if len(username) < 4 or len(username) > 255:
         return jsonify ("Username needs to be between 4 and 255 characters long.")
    
    #check if email is valid

    #another way of doing if else statement

    try:
        # Check that the email address is valid.
        validation = validate_email(email)  
        email = validation.email
    except EmailNotValidError as e:
        # Email is not valid.
        # The exception message is human-readable.
        return jsonify('Email not valid: ' + str(e))

    #username cannot include whitespace
    if any (char.isspace() for char in username):
         return jsonify ('Username cannot have spaces in it.')
    
    #email cannot include whitespace
    if any (char.isspace() for char in email):
         return jsonify('Email cannot have spaces in it.')
    
    # to select all column we will use
    getCountByUsername = '''SELECT COUNT(*) FROM customer WHERE username = %s'''
    cur.execute(getCountByUsername,[username])
    countOfUsername = cur.fetchone()

    if countOfUsername[0] != 0 :
         return jsonify('Username already exists.')
              

    #ready to insert into database
    try:

        insertNewUser = """INSERT INTO customer (email, firstname, lastname, passwd, streetaddress, username, zipcode) VALUES (%s,%s,%s,%s,%s,%s,%s)"""
        cur.execute(insertNewUser, [email, firstname, lastname, passwd, streetaddress, username, zipcode])
        conn.commit()

        msg = jsonify('Query inserted successfully')
        msg.headers['Access-Control-Allow-Methods'] = 'POST'
        msg.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        msg.headers['Access-Control-Allow-Origin'] = 'https://shoe-st.vercel.app/'


    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (insertNewUser, str(err))
        conn.rollback()
        return jsonify ( msg)        
    finally:
        cur.close()

    return msg

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)