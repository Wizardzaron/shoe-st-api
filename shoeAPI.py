# import psycopg2
import os
from flask import Flask, render_template, request, redirect, url_for, session, abort, make_response, current_app, jsonify
from datetime import date, datetime, timedelta
from flask import send_from_directory
from functools import wraps
from email_validator import validate_email, EmailNotValidError
import sys
import psycopg2
from flask_cors import CORS
from collections import defaultdict
from flask_apscheduler import APScheduler

import random
import smtplib
import jwt
import logging
import hashlib
import json


#creates the flask object
app = Flask(__name__)

# supports_credentials allows us to use  include the Access-Control-Allow-Credentials header in the response. thus letting us to send cookies(thus allowing us to properly use sessions) or http authentication
CORS(app, supports_credentials=True)

app.config['SECRET_KEY'] = 'Sa_sa'
# need this for the server side so the cookies containing the id for sessions dont get blocked
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_FILE_DIR'] = "."


app.permanent_session_lifetime = timedelta(minutes=120)

sched = APScheduler()

class Config:
    SCHEDULER_API_ENABLED = True

app.config.from_object(Config())

sched.init_app(app)
sched.start()

def connect_to_database():

    #learn how to connect with URL

    conn = psycopg2.connect(
        os.environ.get('DATABASE_URL'),
        
        #units are in seconds
        keepalives_idle=180,
        connect_timeout=2 
    )
    
    return conn
    
    # conn = sqlite3.connect("shoe.db", check_same_thread=False)

def checkURL():
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    
    cur = conn.cursor()
    
    FRONTEND = os.environ.get('FRONTEND_URL')
    getUrl = '''SELECT * FROM validdomains'''
    cur.execute(getUrl)

    info = cur.fetchall()
    for row in info:
        print(row[0])
        if row[0] == FRONTEND:
            return jsonify("True")



    return jsonify("False")
    
def deletePasscode():

    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    
    cur = conn.cursor()
    changePass = '''UPDATE customer SET temporarypasscode = null, codedate = null'''
    cur.execute(changePass)
    conn.commit()

#The Simple Mail Transfer Protocol (SMTP) is a technical standard for transmitting electronic mail (email) over a network.

def sendEmail(username, code, customerObjEmail):
    
    HOST = "smtp.gmail.com"
    PORT = 587
    FROM_EMAIL = "test.t94714808@gmail.com"
    TO_EMAIL = customerObjEmail['email']
    PASSWORD = os.environ.get('SENDER_PASSWORD')

    MESSAGE = "From: " + FROM_EMAIL + "\r\n" 
    MESSAGE += "To: " + TO_EMAIL + "\r\n"
    MESSAGE += "Subject: " + "Password recovery code" + "\r\n"
    MESSAGE += "\r\n"
    MESSAGE += "Hi There {Username}".format(Username=username) + "\r\n"
    MESSAGE += "  " + "\r\n"
    MESSAGE += "Here is your password recovery code {code} ,it'll expire in one hour".format(code=code) + "\r\n"
    MESSAGE += "  " + "\r\n"
    MESSAGE += "Thanks, Fake Email" + "\r\n"

    s = smtplib.SMTP(HOST, PORT)

    #elho() tells the server that the user is a SMTP client
    status_code, response = s.ehlo()
    print(f"[*] Echoing the server: {status_code} {response}")


    #StartTLS is a protocol command used to inform the email server that the email client wants to upgrade 
    # from an insecure connection to a secure one using TLS or SSL. 
    status_code, response = s.starttls()
    print(f"[*] Starting tls connection: {status_code} {response}")


    status_code, response = s.login(FROM_EMAIL, PASSWORD)
    print(f"[*] Logging in: {status_code} {response}")


    s.sendmail(FROM_EMAIL, TO_EMAIL, MESSAGE)
    s.quit() 
    

def hashingThePassword(password):
    
    print("Hashing the password:" + password)
    pass_bytes = password.encode('utf-8')
    
    #256 does not encrypt, it hashs the values
    #convert into a string
    hashPass = hashlib.sha256(pass_bytes)
    # print(hashPass.digest())
    
    stringPass = str(hashPass.digest())
    
    return stringPass

def fetchObjectFromCursorAll(cursor):

    tuple = cursor.fetchall()
    # print(tuple)
    # print("description",cursor.description)
    # print(len(tuple))

    # need the array to store the shoe sizes because object dictionary keeps getting overwritten through every iteration
    obs = []
    #obs = dict()
    for i in range(len(tuple)):
        # need to put dict in outer for loop in order to prevent shoe sizes from being overridden with the last values
        obj = dict()
        # needed the inner for loop in order to iterate through each array in the tuple
        for element in range(len(tuple[i])):
            # print(f"The element at index {element} is {tuple[i][element]}")
            obj[cursor.description[element][0]] = tuple[i][element]
        obs.append(obj)
        #obs[i] = obj
    return obs


def fetchObjectFromCursor(cursor):

    tuple = cursor.fetchone()
    if tuple is None:
        return None

    obj = dict()
    for i in range(len(tuple)):
        # print(f"The element at index {i} is {tuple[i]}")
        obj[cursor.description[i][0]] = tuple[i]

    return obj


@app.route('/connect', methods=['GET'])
def check_connection():
    
    conn = connect_to_database()
    # connection = conn.closed
    # if (connection != 0):
    if conn is None:    
        return jsonify({"message": "No connection"}), 503

    else:
        return jsonify({"message": "Connection is established"}), 200

@app.route('/cartitem', methods=['GET','POST', 'PATCH'])
def itemdata_post():

    
    conn = connect_to_database()
    if conn is None:
        print("Unable to connect to database")
        return jsonify({"message": "No connection"}), 503
    
    cur = conn.cursor()

    data = request.json


    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)

    print("Cart item request data: " + json.dumps(data))

    size_id = int(data.get('size_id'))
    shoe_id = int(data.get('shoe_id'))
    customer_id = session['id']
    print("/cartitem: customer: ", customer_id, " session: ", session['id'], " size_id: ", size_id)

    cart_id = 0
    try:
        getCartItem = """SELECT cart_id FROM cart WHERE customer_id = %s"""
        cur.execute(getCartItem, [customer_id])
        row = cur.fetchone()
        if row is not None:
            cart_id = row[0]
        else:                
            #returning allows us to retrieve the values from the same query without needing to make a new one,
            # In an INSERT, the data available to RETURNING is the row as it was inserted.
            insertCustomerCart = """INSERT INTO cart (customer_id) VALUES (%s) RETURNING cart_id"""
            cur.execute(insertCustomerCart, (customer_id,))
            cart_id = cur.fetchone()[0]
    except Exception as err:
        msg = 'Select Query Failed: %s\nError: %s' % (getCartItem, str(err))
        return jsonify(msg)
    
    print(cart_id)
    
    
    # If number of affected rows == 0 THEN
    # INSERT INTO CART (….qty) VALUES (....1)
    # Update cart set qy=qty+1. Where shoe=x and size=y and cartid=z
    
    
    #THE PROBLEM IS THAT FOR THE ON CONFLICT CLAUSE I NEED A UNIQUE CONSTRAINT, MAYBE THERE'S A WAY TO INSERT USING CART_ID?
    
    try:
        addCartItem = """INSERT INTO cartitems (cart_id, size_id, shoe_id,quantity) VALUES (%s,%s,%s, 1) ON CONFLICT (shoe_id,cart_id,size_id) 
        DO UPDATE SET quantity = cartitems.quantity + 1 WHERE cartitems.shoe_id = %s"""
        
        cur.execute(addCartItem,[cart_id,size_id,shoe_id, shoe_id])
        conn.commit()
                  
    except Exception as err:
        msg = 'Insert Query Failed: %s\nError: %s' % (addCartItem, str(err))
        return jsonify(msg)
    


    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = jsonify('Trying to retrieve session')
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    
    #create a env for url
    
    #another method is to create a table for permitted urls
    
    #how to use http header to get domain name
    
    msg.headers['Access-Control-Allow-Origin'] = url
    
    return msg

@app.route('/cartitems', methods=['GET'])
def itemdata_get():
    
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()
    customer_id = session['id']

    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)

    try:
        getItem = '''
            SELECT DISTINCT i.image_url, i.image_id ,sd.shoe_name,sd.id ,sd.price, sd.sex, sd.color, sz.size, sz.size_id, bd.brand_name, ct.cart_id ,cts.cart_item_id, cts.quantity
            FROM image AS i, shoe AS sd, sizes as sz ,brand AS bd, cart AS ct, cartitems AS cts
            WHERE i.main_image = 1
            AND  ct.customer_id = %s
            AND i.shoe_id = sd.id 
            AND sd.brand_id = bd.brand_id 
            AND ct.cart_id = cts.cart_id 
            AND cts.size_id = sz.size_id 
            AND sz.shoe_id = sd.id'''
        cur.execute(getItem,[customer_id])
        shoeObjItem = fetchObjectFromCursorAll(cur)   
        
        subTotal = 0
        
        for item in shoeObjItem:
            # Check if the key exists in the dictionary
            if "price" in item:
                # Access the value associated with the key
                subTotal += item["price"] * item["quantity"]
          
        data = {"subTotal": subTotal}      
    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (getItem, str(err))
        return jsonify(msg)
   
    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = make_response(jsonify(shoeObjItem, data))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url
    
    return msg


@app.route('/getcartdata', methods=['GET'])
def cartdata_get():

    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()

    customer_id = session['id']

    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
    
    try:
        getCartItem = """SELECT cart_id FROM cart WHERE customer_id = %s"""
        cur.execute(getCartItem, [customer_id])
        customerCartData = fetchObjectFromCursor(cur)

    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (getCartItem, str(err))
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = make_response(jsonify(customerCartData))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url
    
    return msg

@app.route('/cartdataremoved', methods=['DELETE'])
def cartdata_delete():
    
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()

    customer_id = request.form.get('customer_id')

    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
    
    try:
        deleteCustomerCart = """DELETE FROM cart WHERE customer_id = %s"""
        cur.execute(deleteCustomerCart, [customer_id])
        conn.commit()
    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (deleteCustomerCart, str(err))
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = jsonify('Cart Deleted')
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url  
    
    return msg

@app.route('/cartitemid', methods=['GET'])
def cartitemid_get():
    
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    
    cur = conn.cursor()
    
    cart_id = request.form.get('cart_id')
    size_id = request.form.get('size_id')
    
    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
        
    try:
        cartId = """SELECT cart_item_id FROM cartitems WHERE cart_id = %s AND size_id = %s"""
        cur.execute(cartId, [cart_id, size_id])
        cartObjId = fetchObjectFromCursorAll(cur)
    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (cartId, str(err))
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = make_response(jsonify(cartObjId))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url

    return msg

@app.route('/cartitemremoved', methods=['DELETE'])
def cartitem_delete():

    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    
    cur = conn.cursor()
    
    data = request.json

    cart_item_id = data.get('cart_item_id')
    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
            
    try:
        deleteCartItem = """DELETE FROM cartitems WHERE cart_item_id = %s"""
        cur.execute(deleteCartItem, [cart_item_id])
        conn.commit()
    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (deleteCartItem, str(err))
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = jsonify('Cart Item Deleted')
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url     

    return msg

@app.route('/checkshippingaddress', methods=['GET'])
def shippingaddress_check():

    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    
    cur = conn.cursor()
    customer_id = session['id'] 

    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)

    try:
        getAddress = """SELECT city,state,streetaddress,zipcode,email,firstname,lastname FROM customer WHERE id = %s"""
        cur.execute(getAddress,[customer_id])
        addressObj = fetchObjectFromCursor(cur)
        for index in addressObj:
            if (addressObj[index] is None):
                msg = jsonify(None)
                break
        else:        
            msg = jsonify(addressObj)

    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (getAddress, str(err))
        return jsonify(msg) 
    
    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 
      
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url 
    
    return msg
    
    
# @app.route('/checkusername', methods=['GET'])
# def username_check():

#     
#     conn = connect_to_database()
#         connect_to_database()
#         if conn is None:
#             return jsonify({"message": "No connection"}), 503
        
#     cur = conn.cursor()

#     username = request.form.get('username')
#     print(username)

#     try:
#         getUserItem = """SELECT COUNT(*) FROM customer WHERE username = ?"""
#         cur.execute(getUserItem, [username])
#         customerObjEmail = fetchObjectFromCursor(cur)
#         print(customerObjEmail['COUNT(*)'])
        
#     except Exception as err:
#         msg = 'Query Failed: %s\nError: %s' % (getUserItem, str(err))
#         return jsonify(msg)

#     if customerObjEmail['COUNT(*)'] == 0:
#         s = 0
#         t = '{' + f'"exist":"{str(s)}"' + '}'
#     else:
#         s = 1
#         t = '{' + f'"exist":"{str(s)}"' + '}'

#     return jsonify(t)

#check
@app.route('/passwordchange', methods=['GET', 'PATCH'])
def password_change():
    
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    
    cur = conn.cursor()
            
    password = request.args.get('password')
    username = request.args.get('username')
    print(password)
    #hashing helps prevent people from understanding the password and helps with logging in because it hash the value the exact same way
    hashpass = hashingThePassword(password)
    print("hash value: " + str(hashpass))
        
    try:

        changePass = '''UPDATE customer SET passwd = %s WHERE username = %s'''
        cur.execute(changePass, [hashpass, username])
        conn.commit()

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (changePass, str(e))
        return jsonify(msg)
    
    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None     
    
    return jsonify("Password changed sucessfully")

#check
@app.route('/passwordcode', methods=['GET', 'PATCH'])
def passwordcode_check():

    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()

    print("I'm here")

    passwordcode = request.args.get('passwordcode')
        
    passwordcode = int(passwordcode)
    
    username = request.args.get('username')
    
    msg = jsonify('False')

    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
        
    try:
        getPasscode = """SELECT temporarypasscode, codedate FROM customer WHERE username = %s"""
        cur.execute(getPasscode, [username])
        customerObjCode = fetchObjectFromCursor(cur)
        retrievedPass = customerObjCode["temporarypasscode"]
        retrievedDate = customerObjCode["codedate"]

        print(retrievedDate)

    except Exception as err:
        # msg = 'Query Failed: %s\nError: %s' % (getPasscode, str(err))
        # return jsonify(msg)
        pass

    #need to create an object in order to use timedelta
    # date_object = datetime.strptime(retrievedDate, "%Y-%m-%d %H:%M:%S.%f")
    # print(date_object)
    date_object = retrievedDate

    result = date_object + timedelta(hours=1)

    print (result)

    now = datetime.now()
    try:
        if now > result:
            nullifyCode = """UPDATE customer SET temporarypasscode = NULL, codedate = NULL WHERE username = %s"""
            cur.execute(nullifyCode, [username])
            conn.commit()
        else:
            if passwordcode == retrievedPass:
                nullifyCode = """UPDATE customer SET temporarypasscode = NULL, codedate = NULL WHERE username = %s"""
                cur.execute(nullifyCode, [username])
                conn.commit()    
                msg = jsonify("True")          


    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (getPasscode, str(err))
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Origin'] = url    

    print(msg)
    
    return msg

#check
@app.route('/sendemail', methods=['GET', 'PATCH'])
def sendemail_send():

    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    
    cur = conn.cursor()
        
    username = request.args.get('username')
    print(username)
    print("Hi")
    
    code = random.randrange(100000,999999)
    now = datetime.now()

    #use .split to retrieve multiple urls and use ; as my parameter

    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
                    
    try:
        getEmailItem = """SELECT EMAIL FROM customer WHERE username = %s"""
        cur.execute(getEmailItem, [username])
        customerObjEmail = fetchObjectFromCursor(cur)
        if customerObjEmail is not None:
            sendEmail(username, code, customerObjEmail)

    except Exception as err:
        pass

    try:
        sendPassCode = """UPDATE customer SET temporarypasscode = %s, codedate = %s WHERE username = %s"""
        cur.execute(sendPassCode, [code,now,username])
        conn.commit()
    except Exception as err:
        pass
    
    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 
    
    response = jsonify({"code": code})
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Origin'] = url
    print(response)
    
    return response

    
@app.route('/changeshoesize', methods=['PATCH'])
def changeshoesize_update():
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    
    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)

    cur = conn.cursor()   


    size_id = request.args.get('id')
    cart_item_id = request.args.get('cart_item_id')
    print(size_id)

    try:
        sendPassCode = """UPDATE cartitems SET size_id = %s WHERE cart_item_id = %s"""
        cur.execute(sendPassCode, [size_id,cart_item_id])
        conn.commit()
    except Exception as err:
        pass
    
    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = jsonify("Size has changed")
    msg.headers['Access-Control-Allow-Methods'] = 'PATCH'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url
    
    return msg    



# @app.route('/updateshoe', methods=['PATCH'])
# def shoedata_update():
#     
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
#     
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

#check
@app.route('/allsizes', methods=['GET'])
def allsizes_get():
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()   
    
    shoe_id = request.args.get('id')
    print(shoe_id)
    
    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
    
    try:

        getSize = '''SELECT size,size_id FROM sizes WHERE shoe_id = %s AND in_stock > 0'''
        cur.execute(getSize, [shoe_id])
        shoeObjSize = fetchObjectFromCursorAll(cur)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getSize, str(e))
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = make_response(jsonify(shoeObjSize))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url
    
    return msg
    
#check
@app.route('/shoeimages', methods=['GET'])
def shoeimages_get():

    # psycopg2 has the .closed attribute but not sqlite3 you need to use None in order to check for a closed connection
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()

    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
    
    try:

        getImage = '''SELECT shoe_id, image_id, image_url FROM image'''
        cur.execute(getImage)
        shoeObjImages = fetchObjectFromCursorAll(cur)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getImage, str(e))
        # used to reset connection after bad query transaction
        # conn.rollback()
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = make_response(jsonify(shoeObjImages))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url

    return msg
@app.route('/allshoecolors', methods=['GET'])
def allshoecolors_get():
    
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()
    
    url = os.environ.get('FRONTEND_URL')
    
    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
    
    try:   
        #I need to find a way to retrieve all the shoe color image for the shoe but also make sure they are split into their 
        # respective shoes, and that they aren't the different images

        #needed to include JOIN clause to stop cartesian product from returning duplicate values
        getColors = '''
        SELECT  i.image_id, i.image_url, i.main_image, i.brand_id
        FROM image as i
        JOIN brand as bd ON i.brand_id = bd.brand_id
        WHERE i.main_image = 1'''

        cur.execute(getColors)
        shoeObj = fetchObjectFromCursorAll(cur)
        
        dickTucker = defaultdict(list)
        
        for shoes in shoeObj:
            brand_id = shoes['brand_id']
            #uses brand_id as our key to append the appropriate values
            dickTucker[brand_id].append(shoes)
            
        #wraps it into a dictionary to help retrieve the values in the front end
        organizedColors = dict(dickTucker)
        
        print(organizedColors)
        # for key, value in organizedColors.items():
        #     print(key)
        #     for item in value:
        #         print(item)
                    
    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getColors, str(e))
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 
    msg = make_response(jsonify(organizedColors))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url

    return msg

#in postgresql if you want to use GROUP BY it needs to be applied to all attributes

@app.route('/allshoes', methods=['GET'])
def allshoes_get():
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()
    
    url = os.environ.get('FRONTEND_URL')
        
    try:
        response = checkURL()
        print(response)
        
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
    
    
    try:

        #needed to include JOIN clause to stop cartesian product from returning duplicate values
        #need to fix the query to retrieve two distinct records
        getInfo = '''
        SELECT DISTINCT ON 
            (b.brand_id)
            b.brand_id,
            sd.sex, 
            sd.descript,
            sd.id, 
            sd.shoe_name,
            b.brand_name 
        FROM shoe AS sd
        JOIN brand AS b ON b.brand_id = sd.brand_id
        ORDER BY b.brand_id '''

        cur.execute(getInfo)
        brandObjects = fetchObjectFromCursorAll(cur)
        for brand in brandObjects:
            brand_id = brand["brand_id"]
            getImages = '''
            SELECT
                sd.brand_id, 
                sd.id,
                sd.price,
                sd.color,
                sd.color_order, 
                i.image_id, 
                i.image_url 
            FROM shoe AS sd
            JOIN image as i ON i.shoe_id = sd.id 
            WHERE sd.brand_id = %s AND i.main_image = 1
            ORDER BY sd.color_order'''
            cur.execute(getImages,[brand_id])
            brand["images"] = fetchObjectFromCursorAll(cur)
            
    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getInfo, str(e))
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = make_response(jsonify(brandObjects))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url

    return msg
    
    
#check
@app.route('/allmainimages', methods=['GET'])
def mainimages_get():

    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()

    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
    
    try:

        # this a join
        getImage = '''
        SELECT i.shoe_id, i.image_id, i.image_url, sd.shoe_name, sd.descript, bd.brand_name , bd.brand_id
        FROM image AS i, shoe AS sd, brand AS bd 
        WHERE i.main_image = 1 AND i.shoe_id = sd.id AND sd.brand_id = bd.brand_id'''

        cur.execute(getImage)
        shoeObjImages = fetchObjectFromCursorAll(cur)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getImage, str(e))
        # used to reset connection after bad query transaction
        # conn.rollback()
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = make_response(jsonify(shoeObjImages))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url

    return msg

#check?
@app.route('/differentshoecolors', methods=['GET'])
def differentshoecolors_get():

    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()
    rows = []
    
    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
        
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
                sd.id = %s AND 
                sd.id = i.shoe_id AND 
                i.main_image = 1 AND 
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

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = make_response(jsonify(rows))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url

    return rows

#rename to shoebrands
@app.route('/allshoedata', methods=['GET'])
def allshoedata_get():
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()

    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
    
    try:

        getData = '''SELECT sd.id, sd.color, sd.sex, sd.price, sd.descript, sd.shoe_name, b.brand_id,b.brand_name, i.shoe_id, i.image_id, i.image_url
        FROM shoe AS sd, brand AS b, image AS i
        WHERE i.main_image = 1 AND i.shoe_id = sd.id AND sd.brand_id = b.brand_id'''
        cur.execute(getData)
        shoeObjList = fetchObjectFromCursorAll(cur)


    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getData, str(e))
        # used to reset connection after bad query transaction
        # conn.rollback()
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = make_response(jsonify(shoeObjList))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url

    return msg

#check
@app.route('/shoedata', methods=['GET'])
def shoedata_get():
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()
    
    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
        
    try:

        shoe_id = request.args.get('id')
        print(shoe_id)
        getInfo = '''
        SELECT sd.color, sd.sex, sd.price, sd.descript, sd.shoe_name , b.brand_name, b.brand_id
        FROM shoe AS sd, brand AS b
        WHERE sd.id = %s AND b.brand_id = sd.brand_id'''

        cur.execute(getInfo, [shoe_id,])
        shoeObj = fetchObjectFromCursor(cur)

        getSizes = '''SELECT size, size_id, in_stock FROM sizes WHERE shoe_id = %s'''

        cur.execute(getSizes, [shoe_id,])
        shoeObj["sizes"] = fetchObjectFromCursorAll(cur)

        getBrand = '''SELECT i.image_url, i.shoe_id FROM image as i, shoe as sd WHERE i.main_image = 1 AND 
        i.shoe_id = sd.id AND sd.brand_id = %s'''
        cur.execute(getBrand, [shoeObj["brand_id"],])
        shoeObj["brand_images"] = fetchObjectFromCursorAll(cur)

        getImage = ''' SELECT shoe_id, image_id, image_url, main_image FROM image WHERE shoe_id = %s'''
        cur.execute(getImage, [shoe_id])
        shoeObj["images"] = fetchObjectFromCursorAll(cur)
        print(shoeObj)

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getSizes, str(e))
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    msg = make_response(jsonify(shoeObj))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url

    return msg


@app.route('/shoebrand', methods=['GET'])
def shoebrand_get():
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()
  
    url = os.environ.get('FRONTEND_URL')
    
    try:

        response = checkURL()
        
        if not response:
            abort(403)   

        manufacture = request.args.get('manufacture_id')
        # itemId = 'FB7582-001'
        # print(itemId)       
        
        getInfo = '''SELECT DISTINCT ON (sd.shoe_name) sd.shoe_name, md.manufacture_name, b.brand_name, sd.sex, sd.price, sd.id, i.image_url, i.image_id
        FROM shoe AS sd
        JOIN manufacture AS md ON sd.manufacture_id = md.manufacture_id 
        JOIN brand AS b ON sd.brand_id = b.brand_id 
        JOIN image AS i ON i.shoe_id = sd.id
        WHERE sd.manufacture_id = %s 
        AND i.main_image = 1 
        AND i.shoe_id = sd.id 
        ORDER BY sd.shoe_name'''
    
        
        
        cur.execute(getInfo, [manufacture])
        brandObj = fetchObjectFromCursorAll(cur)



    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getInfo, str(e))
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 
    
    
    msg = make_response(jsonify(brandObj))
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url
    
    return msg
        
# @app.route('/search', methods=['GET'])
# def search():

#     cur = conn.cursor()

#     try:

#         searching = request.args.get('searchValue')


@app.route('/login', methods=['GET', 'POST'])
def login():
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()

    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)


    try:

        msg = jsonify('Query inserted successfully')
        msg.headers['Access-Control-Allow-Methods'] = 'GET'
        msg.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        msg.headers['Access-Control-Allow-Origin'] = url
        msg.headers['Access-Control-Allow-Credentials'] = True

        username = request.args.get('username')
        passwd = request.args.get('passwd')

        print(username, passwd)
        encrpytedPassword = hashingThePassword(passwd)
        # NOTE in sqlite and postgresql you use %s as placeholders instead of ?

        getCountByUsernameAndPassword = '''SELECT count(*) FROM customer WHERE username = %s AND passwd = %s'''
        cur.execute(getCountByUsernameAndPassword, [username, encrpytedPassword])

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

        getId = '''SELECT id FROM customer WHERE username = %s AND CAST (passwd AS TEXT) = %s'''
        cur.execute(getId, [username, encrpytedPassword])
        retrieved_id = cur.fetchone()

        # sessions carry data over the website
        session['loggedin'] = 'True'

        session['username'] = username

        # need to do retrieved_id[0] because even though their is only one id number we are retrieving it's still wrapped in a tuple
        # and needs to be removed
        session['id'] = str(retrieved_id[0])

        # print("Id: ", id)
        print("session id does exist in session: ", session.get('id'))

        s = str(session['loggedin'])
        i = session['id']
        t = '{' + f'"loggedin":"{str(s)}", "id":"{i}"' + '}'
        print(session)
        print(t)
        conn.close()
        return t

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getId, str(e))
        conn.rollback()
        conn.close()
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

@app.route('/newquantity', methods=['PATCH'])
def newquantity_patch():
    
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()

    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)    
      
    try:

        msg = jsonify('Quantity has been updated')
        msg.headers['Access-Control-Allow-Methods'] = 'PATCH'
        msg.headers['Access-Control-Allow-Origin'] = url

        cartId = request.args.get("cart_item_id")
        quantity = request.args.get("newQuantity")

        updateQuantity = '''UPDATE cartitems SET Quantity = %s WHERE cart_item_id = %s'''
        cur.execute(updateQuantity, [quantity,cartId])
        conn.commit()

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (updateQuantity, str(e))
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    return msg

@app.route('/totalcost', methods=['GET'])
def totalcost_get():
    print("arrived at total cost endpoint")
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    msg = 0
    try:
        print("doing total cost calculation")
        arrayOfprice = request.args.get("prices")
        splitPrice = arrayOfprice.split(',')
        prices = [float(price) for price in splitPrice] 
        arrayOfQuantity = request.args.get("quantity")
        splitQuantity = arrayOfQuantity.split(',')
        quantitys = [float(quantity) for quantity in splitQuantity] 

        for index in range(len(prices)):
            msg += prices[index] * quantitys[index]        
            # print(prices[index])
        
        print(msg)

    except Exception as e:
        msg = str(e)
        return jsonify(msg)

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    return str(msg)


@app.route('/userdata', methods=['GET'])
def userdata_get():
    
    if not conn or conn.closed:
        connect_to_database()
        if conn.closed:
            return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()
    rows = []
    
    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
        
    try:
        msg = jsonify('Query inserted successfully')
        msg.headers['Access-Control-Allow-Methods'] = 'GET'
        msg.headers['Access-Control-Allow-Credentials'] = 'true'
        msg.headers['Access-Control-Allow-Origin'] = url

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

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

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

    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 

    return rows

@app.route('/orderdelete', methods=['DELETE'])
def order_delete():

    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()

    order_id = request.args.get('order_id')
    
    try:
        
        deleteOrder = """DELETE FROM orders WHERE order_id = %s"""
        cur.execute(deleteOrder, [order_id])
        conn.commit()
        
    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (deleteOrder, str(err))
        conn.rollback()
        return jsonify(msg)

    finally:
        conn.close()
        conn = None 
        
    return jsonify('order deleted successfully')

@app.route('/ordercreate', methods=['POST', 'PATCH', 'DELETE'])
def order_post():
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503
    cur = conn.cursor()

    total = request.args.get('total')
    cart_id = request.args.get('cart_id')

    today = date.today()
    dateoforder = today

    id = session["id"]

    try:

        insertNewOrder = """INSERT INTO orders (order_date,total) VALUES (%s,%s) RETURNING order_id"""
        cur.execute(insertNewOrder, [dateoforder, total])
        order_id = cur.fetchone()[0]
        conn.commit()

    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (insertNewOrder, str(err))
        conn.rollback()
        return jsonify(msg)

    try:
        updateCustomerOrder = """UPDATE customer SET orderid = %s WHERE id = %s """
        cur.execute(updateCustomerOrder, [order_id, id])
        conn.commit()

    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (updateCustomerOrder, str(err))
        conn.rollback()
        return jsonify(msg)       

    try:
        deleteCartItems = """DELETE FROM cartitems WHERE cart_id = %s"""
        cur.execute(deleteCartItems, [cart_id])
        conn.commit()
        
    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (deleteCartItems, str(err))
        return jsonify(msg)


    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 
        
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


    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503

    msg = jsonify('Trying to retrieve session')
    msg.headers['Access-Control-Allow-Credentials'] = 'true'

    print("Hey")
    for key, value in session.items():
        print(f"{key}: {value}")

    # needed to include elif in case the user didn't close down their browser window and wanted to keep using the site

    # if session['loggedin'] == 'False':
    #     s = str(session)
    #     t = jsonify(loggedin=s)
    #     print(t)
    #     return t
    if 'loggedin' in session and session['loggedin'] == 'True':

        s = str(session['loggedin'])
        i = session['id']
        # t = '{' + f'"loggedin":"{str(s)}"' + '}'
        # t = '{' + f'"loggedin":"{str(s)}", "id":"{i}"' + '}'
        t = jsonify(loggedin=s, id=i)
        print(t)
        conn.close()
        # need to do because conn still has a value
        conn = None 
        return t
    else:
        # used to create session loggedin just in case the cookie doesn't exist yet
        print("Session doesn't exist yet")
        session['loggedin'] = 'False'
        s = str(session['loggedin'])
        # t = '{' + f'"loggedin":"{str(s)}"' + '}'
        t = jsonify(loggedin=s)
        print(t)
        conn.close()
        # need to do because conn still has a value
        conn = None 
        return t



@app.route('/logout', methods=['GET'])
def logout():

    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503

    msg = jsonify('Query inserted successfully')
    msg.headers['Access-Control-Allow-Credentials'] = 'true'

    if 'loggedin' in session:

        session.pop('loggedin', None)
        session.pop('id', None)
        t = '{' + f'"Signout": "Successful"' + '}'
    else:
        t = '{' + f'"Signout": "Failure"' + '}'
    conn.close()
    conn = None
    return t


@app.route('/signup', methods=['POST'])
def signup_post():
    
    conn = connect_to_database()
    if conn is None:
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
    city = data.get('city')
    state = data.get('state')

    url = os.environ.get('FRONTEND_URL')

    print(email, firstname, lastname, passwd, streetaddress, username, zipcode, city, state)

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)

    # password must be between 4 and 255
    if len(passwd) < 4 or len(passwd) > 255:
        return jsonify({"message" : "password must be between 4 and 255", "status" : 400}),400

    # username must be between 4 and 255
    if len(username) < 4 or len(username) > 255:
        return jsonify({"message" : "Username needs to be between 4 and 255 characters long.", "status" : 400}),400

    # check if email is valid

    # another way of doing if else statement

    try:
        # Check that the email address is valid.
        validation = validate_email(email)
        email = validation.email
    except EmailNotValidError as e:
        # Email is not valid.
        # The exception message is human-readable.
        return jsonify({"message" : 'Email not valid: ' + str(e), "status" : 400}),400

    # username cannot include whitespace
    if any(char.isspace() for char in username):
        return jsonify({"message" : 'Username cannot have spaces in it.', "status" : 400}),400

    # email cannot include whitespace
    if any(char.isspace() for char in email):
        return jsonify({"message" : 'Email cannot have spaces in it.', "status" : 400}),400

    # to select all column we will use
    getCountByUsername = '''SELECT COUNT(*) FROM customer WHERE username = %s'''
    cur.execute(getCountByUsername, [username])
    countOfUsername = cur.fetchone()

    print("count of identical names: ", countOfUsername[0])

    if countOfUsername[0] != 0:
        return jsonify({"message" : 'Username already exists.', "status" : 400}),400

    encrpytedPassword = hashingThePassword(passwd)

    #in case the user doesn't send the zipcode, it'll check for None and ''
    if not zipcode:
        zipcode = 0
     
    print("This is the zipcode: " + str(zipcode))

        
    # ready to insert into database
    try:

        insertNewUser = """INSERT INTO customer (email, firstname, lastname, passwd, streetaddress, username, zipcode, city, state) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        cur.execute(insertNewUser, [
                    email, firstname, lastname, encrpytedPassword, streetaddress, username, zipcode, city, state])
        conn.commit()

        msg = jsonify("Query inserted successfully")
        msg.headers['Access-Control-Allow-Methods'] = 'POST'
        msg.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        msg.headers['Access-Control-Allow-Origin'] = url
        msg.status_code = 200
        # print(msg.headers['Access-Control-Allow-Origin'])

    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (insertNewUser, str(err))
        print("printing out the error message: " + msg)
        return jsonify(msg)
    finally:
        conn.close()
        # need to do because conn still has a value
        conn = None 
    print("About to return a message" + str(msg.status_code))
    return msg

@app.route('/updateshippingaddress', methods=['PATCH'])
def shippingaddress_patch():
    
    conn = connect_to_database()
    if conn is None:
        return jsonify({"message": "No connection"}), 503

    cur = conn.cursor()

    url = os.environ.get('FRONTEND_URL')

    try:
        response = checkURL()
        
        if not response:
            abort(403)     
    except Exception as err:

        msg = 'Error: %s' % (str(err))
        return jsonify(msg)
    
    msg = jsonify('Query inserted successfully')
    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = url

    data = request.json

    city = data.get('city')
    state = data.get('state')

    if "id" not in session:
        msg = ({"message": "User could not be found due to id returning none"})
        return jsonify(msg)

    id = session.get('id')
    print("id + ", id)
    
    try:
        updateInfo = '''UPDATE customer SET state = %s, city = %s WHERE id = %s'''
        cur.execute(updateInfo, [state, city, id])
        conn.commit()
    except Exception as err:
        msg = 'Query Failed: %s\nError: %s' % (updateInfo, str(err))
        return jsonify(msg)
    finally:
        conn.close()
        conn = None 
    return msg


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    sched.add_job(id='deletePasscode',func=deletePasscode, trigger='interval', hours=24)
    app.run(host='0.0.0.0', port=port)
