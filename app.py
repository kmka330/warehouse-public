# -*- coding: utf-8 -*-
import logging
import os
from functools import wraps

import psycopg2
from flask import Flask, render_template, request, redirect, url_for, flash, session
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db_connection

load_dotenv()

logger = logging.getLogger(__name__)


def get_required_env(name):
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def flash_db_error(user_message, log_message):
    logger.exception(log_message)
    flash(user_message, 'danger')

app = Flask(__name__)
app.secret_key = get_required_env('SECRET_KEY')

@app.route('/favicon.ico')
def favicon():
    return '', 204


def validate_required(fields):
    for name, value in fields.items():
        if not value or not str(value).strip():
            return name
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session or session['role'] not in allowed_roles:
                flash('Brak uprawnień do tej sekcji.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if validate_required({'Login': username, 'Hasło': password}):
            flash('Wszystkie pola są wymagane.', 'danger')
            return render_template('login.html')
        
        conn = get_db_connection()
        if not conn:
            flash('Błąd połączenia z bazą danych.', 'danger')
            return render_template('login.html')
            
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cur.fetchone()
            
            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                return redirect(url_for('dashboard'))
            else:
                flash('Nieprawidłowy login lub hasło.', 'danger')
                
        except psycopg2.Error:
            flash_db_error('Wystąpił problem podczas logowania. Spróbuj ponownie później.',
                           'Database error during login.')
        finally:
            conn.close()        
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Wylogowano pomyślnie.', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/products', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'warehouse', 'sales'])
def products():
    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        if session.get('role') == 'sales':
            flash('Sprzedawcy nie mają uprawnień do dodawania produktów.', 'danger')
            return redirect(url_for('products'))

        name = request.form['name']
        sku = request.form['sku']
        price = request.form['price']
        stock = request.form['stock']
        supplier_id = request.form['supplier_id']
        
        if validate_required({'Nazwa': name, 'SKU': sku, 'Cena': price, 'Stan': stock, 'Dostawca': supplier_id}):
            flash('Wszystkie pola są wymagane.', 'danger')
            return redirect(url_for('products'))
        
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO products (name, sku, price, stock, supplier_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (name, sku, price, stock, supplier_id))
            conn.commit()
            flash('Produkt dodany pomyślnie.', 'success')
        except psycopg2.Error:
            conn.rollback()
            flash_db_error('Nie udało się dodać produktu.', 'Database error while creating product.')
        finally:
            conn.close()
        return redirect(url_for('products'))

    #GET
    try:
        cur = conn.cursor()
        cur.execute("SELECT p.*, s.company_name FROM products p LEFT JOIN suppliers s ON p.supplier_id = s.id ORDER BY p.id")
        products_list = cur.fetchall()
        
        cur.execute("SELECT * FROM suppliers ORDER BY company_name")
        suppliers_list = cur.fetchall()
        
        return render_template('products.html', products=products_list, suppliers=suppliers_list)
    except psycopg2.Error:
        flash_db_error('Nie udało się pobrać listy produktów.', 'Database error while loading products.')
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

@app.route('/suppliers', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'warehouse'])
def suppliers():
    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        company_name = request.form['company_name']
        email = request.form['email']
        
        if validate_required({'Nazwa firmy': company_name, 'Email': email}):
            flash('Wszystkie pola są wymagane.', 'danger')
            return redirect(url_for('suppliers'))
        
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO suppliers (company_name, email) VALUES (%s, %s)", (company_name, email))
            conn.commit()
            flash('Dostawca dodany pomyślnie.', 'success')
        except psycopg2.Error:
            conn.rollback()
            flash_db_error('Nie udało się dodać dostawcy.', 'Database error while creating supplier.')
        finally:
            conn.close()
        return redirect(url_for('suppliers'))
    
    # GET
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM suppliers ORDER BY id")
        suppliers_list = cur.fetchall()
        return render_template('suppliers.html', suppliers=suppliers_list)
    except psycopg2.Error:
        flash_db_error('Nie udało się pobrać listy dostawców.', 'Database error while loading suppliers.')
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

@app.route('/suppliers/edit/<int:id>', methods=['POST'])
@login_required
@role_required(['admin', 'warehouse'])
def edit_supplier(id):
    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('suppliers'))

    company_name = request.form['company_name']
    email = request.form['email']
    
    if validate_required({'Nazwa firmy': company_name, 'Email': email}):
        flash('Wszystkie pola są wymagane.', 'danger')
        return redirect(url_for('suppliers'))
    
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE suppliers 
            SET company_name = %s, email = %s
            WHERE id = %s
        """, (company_name, email, id))
        conn.commit()
        flash('Dostawca zaktualizowany pomyślnie.', 'success')
    except psycopg2.Error:
        conn.rollback()
        flash_db_error('Nie udało się zaktualizować dostawcy.', 'Database error while updating supplier.')
    finally:
        conn.close()
    return redirect(url_for('suppliers'))

@app.route('/suppliers/delete/<int:id>', methods=['POST'])
@login_required
@role_required(['admin', 'warehouse'])
def delete_supplier(id):
    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('suppliers'))

    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM suppliers WHERE id = %s", (id,))
        conn.commit()
        flash('Dostawca usunięty pomyślnie.', 'success')
    except psycopg2.Error as e:
        conn.rollback()
        if 'violates foreign key constraint' in str(e):
            flash('Nie można usunąć dostawcy, ponieważ posiada przypisane produkty.', 'danger')
        else:
            flash_db_error('Nie udało się usunąć dostawcy.', 'Database error while deleting supplier.')
    finally:
        conn.close()
    return redirect(url_for('suppliers'))

@app.route('/users', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def users():
    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        
        if validate_required({'Nazwa użytkownika': username, 'Hasło': password, 'Rola': role}):
            flash('Wszystkie pola są wymagane.', 'danger')
            return redirect(url_for('users'))
        
        password_hash = generate_password_hash(password)
        
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)", 
                        (username, password_hash, role))
            conn.commit()
            flash('Użytkownik dodany pomyślnie.', 'success')
        except psycopg2.Error:
            conn.rollback()
            flash_db_error('Nie udało się dodać użytkownika.', 'Database error while creating user.')
        finally:
            conn.close()
        return redirect(url_for('users'))

    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users ORDER BY id")
        users_list = cur.fetchall()
        return render_template('users.html', users=users_list)
    except psycopg2.Error:
        flash_db_error('Nie udało się pobrać listy użytkowników.', 'Database error while loading users.')
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

@app.route('/users/delete/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_user(id):
    if id == session.get('user_id'):
        flash('Nie możesz usunąć własnego konta.', 'danger')
        return redirect(url_for('users'))

    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('users'))

    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id = %s", (id,))
        conn.commit()
        flash('Użytkownik usunięty pomyślnie.', 'success')
    except psycopg2.Error:
        conn.rollback()
        flash_db_error('Nie udało się usunąć użytkownika.', 'Database error while deleting user.')
    finally:
        conn.close()
    return redirect(url_for('users'))

@app.route('/users/edit/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def edit_user_role(id):
    if id == session.get('user_id'):
        flash('Nie możesz zmienić roli własnego konta.', 'danger')
        return redirect(url_for('users'))

    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('users'))

    role = request.form['role']
    
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET role = %s WHERE id = %s", (role, id))
        conn.commit()
        flash('Rola użytkownika zmieniona pomyślnie.', 'success')
    except psycopg2.Error:
        conn.rollback()
        flash_db_error('Nie udało się zmienić roli użytkownika.', 'Database error while updating user role.')
    finally:
        conn.close()
    return redirect(url_for('users'))

@app.route('/orders', methods=['GET', 'POST'])
@login_required
@role_required(['sales', 'admin', 'warehouse'])
def orders():
    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        if session.get('role') == 'warehouse':
            flash('Magazynierzy nie mają uprawnień do tworzenia zamówień.', 'danger')
            return redirect(url_for('orders'))

        client_name = request.form['client_name']
        product_ids = request.form.getlist('product_ids[]')
        quantities = request.form.getlist('quantities[]')
        
        if validate_required({'Nazwa klienta': client_name}):
            flash('Nazwa klienta jest wymagana.', 'danger')
            return redirect(url_for('orders'))
        
        if not product_ids or not quantities:
            flash('Zamówienie musi zawierać produkty.', 'warning')
            return redirect(url_for('orders'))

        try:
            cur = conn.cursor()
            
            cur.execute("INSERT INTO orders (client_name, created_by) VALUES (%s, %s) RETURNING id",
                        (client_name, session['user_id']))
            order_id = cur.fetchone()['id']
            
            for pid, qty in zip(product_ids, quantities):
                if int(qty) > 0:
                    cur.execute("INSERT INTO order_items (order_id, product_id, quantity) VALUES (%s, %s, %s)",
                                (order_id, pid, qty))
            
            conn.commit()
            flash('Zamówienie złożone pomyślnie.', 'success')
            
        except psycopg2.Error as e:
            conn.rollback()
            error_msg = str(e)
            if 'Not enough stock' in error_msg:
                flash('Błąd: Niewystarczający stan magazynowy dla jednego z produktów.', 'danger')
            else:
                flash_db_error('Nie udało się złożyć zamówienia.', 'Database error while creating order.')
        finally:
            conn.close()
        return redirect(url_for('orders'))

    #GET
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT o.id, o.date, o.client_name, o.status, u.username as created_by_user 
            FROM orders o 
            LEFT JOIN users u ON o.created_by = u.id 
            ORDER BY o.date DESC
        """)
        orders_list = cur.fetchall()
        
        cur.execute("SELECT * FROM products WHERE stock > 0 ORDER BY name")
        products_list = cur.fetchall()
        
        return render_template('orders.html', orders=orders_list, products=products_list)
    except psycopg2.Error:
        flash_db_error('Nie udało się pobrać listy zamówień.', 'Database error while loading orders.')
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

@app.route('/orders/ship/<int:id>', methods=['POST'])
@login_required
@role_required(['sales', 'admin', 'warehouse'])
def ship_order(id):
    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('orders'))

    try:
        cur = conn.cursor()
        cur.execute("SELECT status FROM orders WHERE id = %s", (id,))
        order = cur.fetchone()
        
        if not order:
            flash('Zamówienie nie istnieje.', 'danger')
        elif order['status'] == 'SHIPPED':
            flash('Zamówienie już zostało wysłane.', 'warning')
        else:
            cur.execute("UPDATE orders SET status = 'SHIPPED' WHERE id = %s", (id,))
            conn.commit()
            flash('Status zamówienia zmieniony na WYSŁANO.', 'success')
            
    except psycopg2.Error:
        conn.rollback()
        flash_db_error('Nie udało się zaktualizować statusu zamówienia.',
                       'Database error while shipping order.')
    finally:
        conn.close()
    return redirect(request.referrer or url_for('orders'))




@app.route('/orders/<int:id>')
@login_required
def order_details(id):
    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('dashboard'))
        
    try:
        cur = conn.cursor()
        
        cur.execute("""
            SELECT o.id, o.date, o.client_name, o.status, u.username as created_by_user 
            FROM orders o 
            LEFT JOIN users u ON o.created_by = u.id 
            WHERE o.id = %s
        """, (id,))
        order = cur.fetchone()
        
        if not order:
            flash('Zamówienie nie istnieje.', 'danger')
            return redirect(url_for('dashboard'))
            
        cur.execute("""
            SELECT p.name, p.sku, oi.quantity, p.price, (oi.quantity * p.price) as total_item_value
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """, (id,))
        items = cur.fetchall()
        
        total_value = sum(item['total_item_value'] for item in items)
        
        return render_template('order_details.html', order=order, items=items, total_value=total_value)
    except psycopg2.Error:
        flash_db_error('Nie udało się pobrać szczegółów zamówienia.',
                       'Database error while loading order details.')
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

@app.route('/reports')
@login_required
def reports():
    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('dashboard'))
        
    try:
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM v_order_summary ORDER BY date DESC")
        summary = cur.fetchall()
        
        cur.execute("SELECT * FROM v_bestsellers ORDER BY total_sold DESC")
        bestsellers = cur.fetchall()
        
        cur.execute("SELECT * FROM v_supplier_inventory")
        supplier_inventory = cur.fetchall()

        cur.execute("SELECT * FROM v_sales_by_employee")
        sales_by_employee = cur.fetchall()
        
        cur.execute("SELECT * FROM v_low_stock")
        low_stock = cur.fetchall()
        
        cur.execute("SELECT * FROM v_worst_sellers")
        worst_sellers = cur.fetchall()
        
        return render_template('reports.html', 
                             summary=summary, 
                             bestsellers=bestsellers,
                             supplier_inventory=supplier_inventory,
                             sales_by_employee=sales_by_employee,
                             low_stock=low_stock,
                             worst_sellers=worst_sellers)
    except psycopg2.Error:
        flash_db_error('Nie udało się pobrać raportów.', 'Database error while loading reports.')
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

@app.route('/products/edit/<int:id>', methods=['POST'])
@login_required
@role_required(['admin', 'warehouse'])
def edit_product(id):
    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('products'))

    name = request.form['name']
    sku = request.form['sku']
    price = request.form['price']
    stock = request.form['stock']
    supplier_id = request.form['supplier_id']
    
    if validate_required({'Nazwa': name, 'SKU': sku, 'Cena': price, 'Stan': stock, 'Dostawca': supplier_id}):
        flash('Wszystkie pola są wymagane.', 'danger')
        return redirect(url_for('products'))
    
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE products 
            SET name = %s, sku = %s, price = %s, stock = %s, supplier_id = %s
            WHERE id = %s
        """, (name, sku, price, stock, supplier_id, id))
        conn.commit()
        flash('Produkt zaktualizowany pomyślnie.', 'success')
    except psycopg2.Error:
        conn.rollback()
        flash_db_error('Nie udało się zaktualizować produktu.', 'Database error while updating product.')
    finally:
        conn.close()
    return redirect(url_for('products'))

@app.route('/products/history/<int:id>')
@login_required
@role_required(['admin', 'warehouse', 'sales'])
def product_history(id):
    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('products'))
        
    try:
        cur = conn.cursor()

        cur.execute("SELECT name FROM products WHERE id = %s", (id,))
        product = cur.fetchone()
        if not product:
            flash('Produkt nie istnieje.', 'danger')
            return redirect(url_for('products'))
            
        cur.execute("""
            SELECT * FROM price_history 
            WHERE product_id = %s 
            ORDER BY change_date DESC
        """, (id,))
        history = cur.fetchall()
        
        return render_template('price_history.html', history=history, product_name=product['name'])
    except psycopg2.Error:
        flash_db_error('Nie udało się pobrać historii cen.', 'Database error while loading price history.')
        return redirect(url_for('products'))
    finally:
        conn.close()

@app.route('/products/delete/<int:id>', methods=['POST'])
@login_required
@role_required(['admin', 'warehouse'])
def delete_product(id):
    conn = get_db_connection()
    if not conn:
        flash('Błąd połączenia z bazą.', 'danger')
        return redirect(url_for('products'))

    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM products WHERE id = %s", (id,))
        conn.commit()
        flash('Produkt usunięty pomyślnie.', 'success')
    except psycopg2.Error as e:
        conn.rollback()
        if 'violates foreign key constraint' in str(e):
            flash('Nie można usunąć produktu, ponieważ znajduje się w zamówieniach.', 'danger')
        else:
            flash_db_error('Nie udało się usunąć produktu.', 'Database error while deleting product.')
    finally:
        conn.close()
    return redirect(url_for('products'))

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0')
