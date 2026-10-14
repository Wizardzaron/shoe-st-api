"""Owned cart operations and atomic, server-priced demo checkout."""
from datetime import date
from decimal import Decimal
from flask import Blueprint, abort, jsonify, request, session
from .db import query, execute, transaction
from .validation import body, positive_int, login_required

bp = Blueprint('carts', __name__)


def owned_cart():
    return query('SELECT cart_id FROM cart WHERE customer_id = %s', (session['id'],), one=True)


def owned_item(item_id):
    item = query('''SELECT ci.cart_item_id, ci.cart_id, ci.shoe_id, ci.size_id, ci.quantity
                    FROM cartitems ci JOIN cart c ON c.cart_id = ci.cart_id
                    WHERE ci.cart_item_id = %s AND c.customer_id = %s FOR UPDATE''',
                 (item_id, session['id']), one=True)
    if not item:
        abort(404, 'Cart item not found.')
    return item


def available_size(size_id, shoe_id, quantity):
    size = query('SELECT in_stock FROM sizes WHERE size_id = %s AND shoe_id = %s FOR UPDATE',
                 (size_id, shoe_id), one=True)
    if not size or size['in_stock'] < quantity:
        abort(409, 'The selected size does not have enough stock.')


@bp.get('/connect')
def health():
    query('SELECT 1 AS ok')
    return jsonify(message='Connection is established')


@bp.post('/cartitem')
@login_required
def add_item():
    data = body()
    shoe_id = positive_int(data.get('shoe_id'), 'shoe_id')
    size_id = positive_int(data.get('size_id'), 'size_id')
    with transaction():
        # Serializes cart creation/additions for the same customer.
        if not query('SELECT id FROM customer WHERE id = %s FOR UPDATE', (session['id'],)):
            abort(401, 'Account no longer exists.')
        cart = owned_cart()
        if not cart:
            cart = query('INSERT INTO cart (customer_id) VALUES (%s) RETURNING cart_id',
                         (session['id'],), one=True)
        item = query('''SELECT quantity FROM cartitems WHERE cart_id = %s AND
                        shoe_id = %s AND size_id = %s FOR UPDATE''',
                     (cart['cart_id'], shoe_id, size_id), one=True)
        quantity = (item['quantity'] if item else 0) + 1
        if quantity > 99:
            abort(400, 'Maximum item quantity is 99.')
        available_size(size_id, shoe_id, quantity)
        execute('''INSERT INTO cartitems (cart_id, size_id, shoe_id, quantity)
                   VALUES (%s,%s,%s,1) ON CONFLICT (shoe_id,cart_id,size_id)
                   DO UPDATE SET quantity = cartitems.quantity + 1''',
                (cart['cart_id'], size_id, shoe_id))
    return jsonify('Item added to cart'), 201


@bp.get('/cartitems')
@login_required
def cartitems():
    items = query('''SELECT i.image_url, i.image_id, sd.shoe_name, sd.id, sd.price,
                    sd.sex, sd.color, sz.size, sz.size_id, bd.brand_name, ct.cart_id,
                    cts.cart_item_id, cts.quantity FROM cartitems cts
                    JOIN cart ct ON ct.cart_id = cts.cart_id
                    JOIN shoe sd ON sd.id = cts.shoe_id
                    JOIN sizes sz ON sz.size_id = cts.size_id AND sz.shoe_id = sd.id
                    JOIN brand bd ON bd.brand_id = sd.brand_id
                    LEFT JOIN image i ON i.shoe_id = sd.id AND i.main_image = 1
                    WHERE ct.customer_id = %s ORDER BY cts.cart_item_id''', (session['id'],))
    subtotal = sum((Decimal(str(item['price'])) * item['quantity'] for item in items), Decimal('0'))
    # Retain the existing frontend's [items, {subTotal: ...}] shape.
    return jsonify([items, {'subTotal': subtotal.quantize(Decimal('0.01'))}])


@bp.get('/getcartdata')
@login_required
def getcartdata():
    return jsonify(owned_cart())


@bp.delete('/cartdataremoved')
@login_required
def clear_cart():
    with transaction():
        cart = owned_cart()
        if cart:
            execute('DELETE FROM cartitems WHERE cart_id = %s', (cart['cart_id'],))
            execute('DELETE FROM cart WHERE cart_id = %s AND customer_id = %s',
                    (cart['cart_id'], session['id']))
    return jsonify('Cart Deleted')


@bp.get('/cartitemid')
@login_required
def cartitemid():
    size_id = positive_int(request.args.get('size_id'), 'size_id')
    return jsonify(query('''SELECT ci.cart_item_id FROM cartitems ci
                            JOIN cart c ON c.cart_id = ci.cart_id
                            WHERE c.customer_id = %s AND ci.size_id = %s''',
                         (session['id'], size_id)))


@bp.delete('/cartitemremoved')
@login_required
def remove_item():
    item_id = positive_int(body().get('cart_item_id'), 'cart_item_id')
    with transaction():
        owned_item(item_id)
        execute('DELETE FROM cartitems WHERE cart_item_id = %s', (item_id,))
    return jsonify('Cart Item Deleted')


@bp.patch('/newquantity')
@login_required
def quantity():
    data = body()
    item_id = positive_int(data.get('cart_item_id'), 'cart_item_id')
    amount = positive_int(data.get('newQuantity'), 'newQuantity', 99)
    with transaction():
        item = owned_item(item_id)
        available_size(item['size_id'], item['shoe_id'], amount)
        execute('UPDATE cartitems SET quantity = %s WHERE cart_item_id = %s', (amount, item_id))
    return jsonify('Quantity has been updated')


@bp.patch('/changeshoesize')
@login_required
def change_size():
    data = body()
    item_id = positive_int(data.get('cart_item_id'), 'cart_item_id')
    size_id = positive_int(data.get('id'), 'id')
    with transaction():
        item = owned_item(item_id)
        available_size(size_id, item['shoe_id'], item['quantity'])
        if query('''SELECT cart_item_id FROM cartitems WHERE cart_id = %s AND
                    shoe_id = %s AND size_id = %s AND cart_item_id <> %s''',
                 (item['cart_id'], item['shoe_id'], size_id, item_id)):
            abort(409, 'This size is already in your cart.')
        execute('UPDATE cartitems SET size_id = %s WHERE cart_item_id = %s', (size_id, item_id))
    return jsonify('Size has changed')


@bp.get('/totalcost')
@login_required
def totalcost():
    # Never accept prices or quantities from query parameters as pricing authority.
    items = query('''SELECT s.price, ci.quantity FROM cartitems ci
                    JOIN cart c ON c.cart_id = ci.cart_id JOIN shoe s ON s.id = ci.shoe_id
                    WHERE c.customer_id = %s''', (session['id'],))
    total = sum((Decimal(str(row['price'])) * row['quantity'] for row in items), Decimal('0'))
    return str(total.quantize(Decimal('0.01')))


@bp.post('/ordercreate')
@login_required
def checkout():
    body()  # Explicit empty {} is sufficient; client cart_id/total are ignored.
    with transaction():
        user = query('SELECT id FROM customer WHERE id = %s FOR UPDATE', (session['id'],), one=True)
        if not user:
            abort(401, 'Account no longer exists.')
        cart = owned_cart()
        if not cart:
            abort(409, 'Your cart is empty.')
        items = query('''SELECT ci.cart_item_id, ci.shoe_id, ci.size_id, ci.quantity, s.price
                        FROM cartitems ci JOIN shoe s ON s.id = ci.shoe_id
                        WHERE ci.cart_id = %s ORDER BY ci.size_id FOR UPDATE''', (cart['cart_id'],))
        if not items:
            abort(409, 'Your cart is empty.')
        total = Decimal('0')
        for item in items:
            positive_int(item['quantity'], 'quantity', 99)
            available_size(item['size_id'], item['shoe_id'], item['quantity'])
            if not execute('''UPDATE sizes SET in_stock = in_stock - %s
                              WHERE size_id = %s AND shoe_id = %s AND in_stock >= %s''',
                           (item['quantity'], item['size_id'], item['shoe_id'], item['quantity'])):
                abort(409, 'Stock changed. Please refresh your cart.')
            total += Decimal(str(item['price'])) * item['quantity']
        order = query('INSERT INTO orders (order_date,total) VALUES (%s,%s) RETURNING order_id',
                      (date.today(), total.quantize(Decimal('0.01'))), one=True)
        execute('UPDATE customer SET orderid = %s WHERE id = %s', (order['order_id'], session['id']))
        execute('DELETE FROM cartitems WHERE cart_id = %s', (cart['cart_id'],))
    # This records a demo order; it does not process payment.
    return jsonify('order created successfully'), 201


@bp.delete('/orderdelete')
def orderdelete():
    # Existing schema links only the latest order to a customer. No safe general
    # cancellation/refund implementation exists without order ownership/history.
    abort(403, 'Order deletion is unavailable through the storefront API.')
