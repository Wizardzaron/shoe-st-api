"""Read-only catalog routes; preserve the current storefront's field names."""
from collections import defaultdict
from flask import Blueprint, abort, jsonify, request
from .db import query
from .validation import positive_int

bp = Blueprint('catalog', __name__)


@bp.get('/allsizes')
def sizes():
    shoe_id = positive_int(request.args.get('id'), 'id')
    return jsonify(query('SELECT size,size_id FROM sizes WHERE shoe_id = %s AND in_stock > 0 ORDER BY size_id', (shoe_id,)))


@bp.get('/shoeimages')
def images():
    return jsonify(query('SELECT shoe_id,image_id,image_url FROM image ORDER BY image_id'))


@bp.get('/allshoecolors')
def colors():
    grouped = defaultdict(list)
    for row in query('SELECT image_id,image_url,main_image,brand_id FROM image WHERE main_image = 1 ORDER BY image_id'):
        grouped[row['brand_id']].append(row)
    return jsonify(dict(grouped))


@bp.get('/allshoes')
def shoes():
    # Two queries instead of one extra image query for every brand (N+1).
    products = query('''SELECT b.brand_id,sd.sex,sd.descript,sd.id,sd.shoe_name,b.brand_name
                        FROM shoe sd JOIN brand b ON b.brand_id = sd.brand_id
                        ORDER BY b.brand_id,sd.id''')
    images = query('''SELECT sd.brand_id,sd.id,sd.price,sd.color,sd.color_order,i.image_id,i.image_url
                     FROM shoe sd JOIN image i ON i.shoe_id = sd.id WHERE i.main_image = 1
                     ORDER BY sd.brand_id,sd.color_order,sd.id,i.image_id''')
    grouped = defaultdict(list)
    for image in images:
        grouped[image['brand_id']].append(image)
    brands = {}
    for product in products:
        if product['brand_id'] not in brands:
            product['images'] = grouped[product['brand_id']]
            brands[product['brand_id']] = product
    return jsonify(list(brands.values()))


@bp.get('/allmainimages')
def main_images():
    return jsonify(query('''SELECT i.shoe_id,i.image_id,i.image_url,sd.shoe_name,sd.descript,
                            bd.brand_name,bd.brand_id FROM image i
                            JOIN shoe sd ON sd.id = i.shoe_id JOIN brand bd ON bd.brand_id = sd.brand_id
                            WHERE i.main_image = 1 ORDER BY sd.id,i.image_id'''))


@bp.get('/differentshoecolors')
def different_colors():
    shoe_id = positive_int(request.args.get('id'), 'id')
    return jsonify(query('''SELECT i.image_id,i.image_url,b.brand_name,i.shoe_id,sd.shoe_name
                            FROM shoe sd JOIN image i ON i.shoe_id = sd.id
                            JOIN brand b ON b.brand_id = sd.brand_id
                            WHERE sd.id = %s AND i.main_image = 1 ORDER BY i.image_id''', (shoe_id,)))


@bp.get('/allshoedata')
def all_data():
    return jsonify(query('''SELECT sd.id,sd.color,sd.sex,sd.price,sd.descript,sd.shoe_name,
                            b.brand_id,b.brand_name,i.shoe_id,i.image_id,i.image_url
                            FROM shoe sd JOIN brand b ON b.brand_id = sd.brand_id
                            JOIN image i ON i.shoe_id = sd.id WHERE i.main_image = 1
                            ORDER BY sd.id,i.image_id'''))


@bp.get('/shoedata')
def detail():
    shoe_id = positive_int(request.args.get('id'), 'id')
    shoe = query('''SELECT sd.color,sd.sex,sd.price,sd.descript,sd.shoe_name,b.brand_name,b.brand_id
                    FROM shoe sd JOIN brand b ON b.brand_id = sd.brand_id WHERE sd.id = %s''', (shoe_id,), one=True)
    if not shoe:
        abort(404, 'Shoe not found.')
    shoe['sizes'] = query('SELECT size,size_id,in_stock FROM sizes WHERE shoe_id = %s ORDER BY size_id', (shoe_id,))
    shoe['brand_images'] = query('''SELECT i.image_url,i.shoe_id FROM image i JOIN shoe sd ON sd.id = i.shoe_id
                                   WHERE i.main_image = 1 AND sd.brand_id = %s ORDER BY sd.id,i.image_id''', (shoe['brand_id'],))
    shoe['images'] = query('SELECT shoe_id,image_id,image_url,main_image FROM image WHERE shoe_id = %s ORDER BY image_id', (shoe_id,))
    return jsonify(shoe)


@bp.get('/shoebrand')
def brand():
    manufacturer = positive_int(request.args.get('manufacture_id'), 'manufacture_id')
    products = query('''SELECT sd.shoe_name,md.manufacture_name,b.brand_name,sd.sex,sd.price,sd.id,i.image_url,i.image_id
                        FROM shoe sd JOIN manufacture md ON md.manufacture_id = sd.manufacture_id
                        JOIN brand b ON b.brand_id = sd.brand_id JOIN image i ON i.shoe_id = sd.id
                        WHERE sd.manufacture_id = %s AND i.main_image = 1 ORDER BY sd.shoe_name,sd.id,i.image_id''', (manufacturer,))
    unique = {}
    for product in products:
        unique.setdefault(product['shoe_name'], product)
    return jsonify(list(unique.values()))
