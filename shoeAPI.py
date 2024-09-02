from flask import Flask, render_template, request, redirect, url_for, session, abort, make_response, current_app, jsonify
import psycopg2
import os

app = Flask(__name__)

conn = None


def connect_to_database():

    global conn

    conn = psycopg2.connect(
        host="c9uss87s9bdb8n.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com",
        port=5432,
        dbname="defotaotch91u7",
        user="ube26p60sqahqj",
        password="p57a9046276c45374a551965a6a904b4a46bfe89b0ccc2c39fc902fec68ed19a1",
        #need to figure out units
        #seconds
        keepalives_idle=180,
        connect_timeout=0 
    )

def allshoedata_get():
    global conn
    if not conn or conn is None:
        print("Esatablishing connection")
        connect_to_database()
        print("We think connection is established")
        if conn is None:
            print("Connection sill isn't established")
            return jsonify({"message": "No connection"}), 503
        else:
            print("Connection successfully established")
        
        
    cur = conn.cursor()
    print("We've got a cursor")

    try:

        getData = '''SELECT sd.id, sd.color, sd.sex, sd.price, sd.descript, sd.shoe_name, b.brand_id,b.brand_name, i.shoe_id, i.image_id, i.image_url
        FROM shoe AS sd, brand AS b, image AS i
        WHERE i.main_image = 1 AND i.shoe_id = sd.id AND sd.brand_id = b.brand_id'''
        cur.execute(getData)
        msg = jsonify("Successfully Executed")
        print("Cursor Executed")

    except Exception as e:
        msg = 'Query Failed: %s\nError: %s' % (getData, str(e))
        # used to reset connection after bad query transaction
        # conn.rollback()
        return jsonify(msg)

    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'

    conn.close()
    conn = None
    return msg

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)