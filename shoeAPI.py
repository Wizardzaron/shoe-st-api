from flask import Flask, render_template, request, redirect, url_for, session, abort, make_response, current_app, jsonify
import psycopg2
import os
from flask_apscheduler import APScheduler

app = Flask(__name__)

conn = None

sched = APScheduler()

class Config:
    SCHEDULER_API_ENABLED = True

app.config.from_object(Config())

sched.init_app(app)
sched.start()

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
        keepalives_idle=3600,
        connect_timeout=0 
    )

@app.route('/shoeimages', methods=['GET'])
def shoeimages_get():

    with app.app_context():

        # psycopg2 has the .closed attribute but not sqlite3 you need to use None in order to check for a closed connection
        global conn
        print("Connection value: " + conn)
        
        if not conn or conn is None:
            print("We think connection is established")
            if conn is None:
                print("Connection sill isn't established")
                print("Shoe2")
                return jsonify({"message": "No connection"}), 503
            else:
                print("Connection successfully established")

        cur = conn.cursor()
        try:

            getImage = '''SELECT shoe_id, image_id, image_url FROM image'''
            cur.execute(getImage)
            msg = jsonify("Successfully Executed")
            print("Cursor Executed")

        except Exception as e:
            msg = 'Query Failed: %s\nError: %s' % (getImage, str(e))
            # used to reset connection after bad query transaction
            # conn.rollback()
            return jsonify(msg)
        finally:
            conn.close()
            # need to do because conn still has a value
            conn = None 

    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Credentials'] = 'true'
    msg.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'

    conn.close()
    return msg



@app.route("/allshoedata", methods=["GET"])
def allshoedata_get():
    with app.app_context():

        global conn
        if not conn or conn is None:
            print("Esatablishing connection")
            connect_to_database()
            print("We think connection is established")
            if conn is None:
                print("Connection sill isn't established")
                print("shoe1")
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

        finally:
            conn.close()
            # need to do because conn still has a value
            conn = None     

    msg.headers['Access-Control-Allow-Methods'] = 'GET'
    msg.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'


    return msg

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    sched.add_job(id='deletePasscode',func=allshoedata_get, trigger='interval', minutes=1)
    sched.add_job(id='shoeimages',func=shoeimages_get, trigger='interval', minutes=2)
    app.run(host='0.0.0.0', port=port)