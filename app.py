from flask import Flask, render_template, request, redirect, session, url_for, send_file
from datetime import datetime
import pandas as pd
import os
import csv

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# File paths
PRODUCTS_FILE = "data/products.xlsx"
USER_FILE = "data/users.csv"

# ---------------------- Helpers ----------------------

def load_users():
    users = {}
    with open(USER_FILE, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            users[row['username'].strip()] = {
                'password': row['password'].strip(),
                'role': row['role'].strip()
            }
    return users

def save_users(users):
    with open(USER_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['username', 'password', 'role'])
        writer.writeheader()
        for username, data in users.items():
            writer.writerow({'username': username, **data})

def load_category_items(category_name):
    df = pd.read_excel(PRODUCTS_FILE)
    filtered = df[df['Category'].str.lower() == category_name.lower()].copy()

    today = pd.Timestamp(datetime.today().date())
    if 'Use By Date' in filtered.columns:
        filtered['Use By Date'] = pd.to_datetime(filtered['Use By Date'], errors='coerce')

        def get_expiry_status(date):
            if pd.isna(date):
                return None
            elif date < today:
                return 'expired'
            elif date <= today + pd.Timedelta(days=3):
                return 'soon'
            return None

        filtered['expiry_status'] = filtered['Use By Date'].apply(get_expiry_status)

        filtered['Use By Date'] = filtered['Use By Date'].apply(
            lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else ''
        )

    return None, filtered.to_dict(orient='records')

# ---------------------- Routes ----------------------

@app.route('/')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))

    try:
        df = pd.read_excel(PRODUCTS_FILE)

        if 'Initial Quantity' not in df.columns:
            df['Initial Quantity'] = df['Quantity']
            df.to_excel(PRODUCTS_FILE, index=False)

        df['Used Quantity'] = df['Initial Quantity'] - df['Quantity']
        full_df = df.copy()
        total_products = full_df['Initial Quantity'].sum()

        if 'Use By Date' in df.columns:
            df['Use By Date'] = pd.to_datetime(df['Use By Date'], errors='coerce')
            today = pd.Timestamp(datetime.today().date())
            df = df[(df['Use By Date'].isna()) | (df['Use By Date'] >= today)]

        remaining_products = df['Quantity'].sum()
        used_products = df['Used Quantity'].sum()
        out_of_stock_items = df[df['Quantity'] == 0]

        highest_sale = {}
        if not df.empty:
            top = df.sort_values(by='Used Quantity', ascending=False).iloc[0]
            highest_sale = {
                'Product': top['Item Name'],
                'Category': top['Category'],
                'Used': top['Used Quantity']
            }

        unique_categories = df['Category'].dropna().unique().tolist()
        low_stock_items = df[df['Quantity'] < 15]

        return render_template('index.html',
                               total_products=total_products,
                               unique_categories=unique_categories,
                               remaining_products=remaining_products,
                               used_products=used_products,
                               out_of_stock=out_of_stock_items.to_dict(orient='records'),
                               highest_sale=highest_sale,
                               low_stock=low_stock_items.to_dict(orient='records'))
    except Exception as e:
        print("Dashboard Error:", e)
        return f"Error loading dashboard: {e}"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        USERS = load_users()
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        role = request.form['role'].strip()

        user = USERS.get(username)
        if user and user['password'] == password and user['role'] == role:
            session['username'] = username
            session['role'] = role
            return redirect(url_for('home'))
        else:
            return "<h3>Invalid credentials or role.</h3>", 403
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/users', methods=['GET', 'POST'])
def users():
    if 'username' not in session or session.get('role') != 'admin':
        return "Access denied", 403

    USERS = load_users()
    if request.method == 'POST':
        new_user = request.form['new_username'].strip()
        password = request.form['new_password'].strip()
        role = request.form['new_role'].strip()

        if new_user in USERS:
            return "User already exists", 400

        USERS[new_user] = {'password': password, 'role': role}
        save_users(USERS)
        return redirect('/users')

    return render_template('users.html', users=USERS)
from flask import request, jsonify, session, redirect, url_for

@app.route('/users/delete/<username>', methods=['POST'])
def delete_user(username):
    current_user = session['username']
    if username == current_user:
        return jsonify({"error": "You cannot delete yourself."}), 403
    
    # Delete user logic here
    success = delete_user_by_username(username)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"error": "User not found."}), 404

@app.route('/users/reset-password/<username>', methods=['POST'])
def reset_password(username):
    # Reset password logic here — e.g., set a default or generate a new one
    new_password = "default123"  # or generate securely
    success = reset_user_password(username, new_password)
    if success:
        return jsonify({"success": True, "new_password": new_password})
    else:
        return jsonify({"error": "User not found."}), 404

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'username' not in session:
        return redirect(url_for('login'))

    USERS = load_users()
    current_user = session['username']

    if request.method == 'POST':
        new_password = request.form['new_password'].strip()
        USERS[current_user]['password'] = new_password
        save_users(USERS)
        return redirect(url_for('profile'))

    return render_template('profile.html', user=current_user, role=session['role'])

@app.route('/used-products')
def used_products():
    if 'username' not in session:
        return redirect(url_for('login'))

    df = pd.read_excel(PRODUCTS_FILE)
    df['Used Quantity'] = df['Initial Quantity'] - df['Quantity']
    used_df = df[df['Used Quantity'] > 0][['Category', 'Item Name', 'Used Quantity']]
    used_df = used_df.rename(columns={'Item Name': 'Product'})
    return render_template('usedproducts.html', used_products=used_df.to_dict(orient='records'))

@app.route('/remaining-products')
def remaining_products():
    if 'username' not in session:
        return redirect(url_for('login'))

    df = pd.read_excel(PRODUCTS_FILE)
    if 'Use By Date' in df.columns:
        df['Use By Date'] = pd.to_datetime(df['Use By Date'], errors='coerce')
        today = pd.Timestamp(datetime.today().date())
        df = df[(df['Use By Date'].isna()) | (df['Use By Date'] >= today)]

    remaining_df = df[df['Quantity'] > 0][['Category', 'Item Name', 'Quantity']]
    return render_template('remainingproducts.html', remaining_products=remaining_df.to_dict(orient='records'))

@app.route('/download-excel')
def download_excel():
    if 'username' not in session:
        return redirect(url_for('login'))

    excel_path = os.path.join('data', 'products.xlsx')
    return send_file(excel_path, as_attachment=True)

@app.route('/total-products')
def total_products_view():
    if 'username' not in session:
        return redirect(url_for('login'))

    try:
        df = pd.read_excel(PRODUCTS_FILE)
        df.fillna('', inplace=True)

        # Format Use By Date
        if 'Use By Date' in df.columns:
            df['Use By Date'] = pd.to_datetime(df['Use By Date'], errors='coerce')
            df['Use By Date'] = df['Use By Date'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else '')

        unique_categories = sorted(df['Category'].dropna().unique().tolist())

        return render_template(
            'total_products.html',
            products=df.to_dict(orient='records'),
            unique_categories=unique_categories,
            user_role=session.get('role')  # Pass user role to template
        )

    except Exception as e:
        return f"Error loading total products: {e}"

@app.route('/categories')
def categories():
    if 'username' not in session:
        return redirect(url_for('login'))

    df = pd.read_excel(PRODUCTS_FILE)
    categories = df['Category'].unique()
    category_data = []
    for cat in categories:
        total_qty = df[df['Category'] == cat]['Quantity'].sum()
        category_data.append({'name': cat, 'total_qty': total_qty})

    return render_template('categories.html', categories=category_data)

@app.route('/<category>')
def category_view(category):
    if 'username' not in session:
        return redirect(url_for('login'))

    error, items = load_category_items(category)
    if error:
        return error
    return render_template('category_template.html', items=items, category_name=category.capitalize())

@app.route('/add-product', methods=['GET', 'POST'])
def add_product():
    if 'username' not in session or session.get('role') != 'admin':
        return "Access denied", 403

    if request.method == 'POST':
        item_name = request.form['item_name'].strip()
        category = request.form['category'].strip()
        quantity_str = request.form['quantity'].strip()
        use_by_date = request.form.get('use_by_date', '').strip()
        image_url = request.form.get('image_url', '').strip()

        if not item_name or not category or not quantity_str.isdigit():
            return "Invalid input", 400

        quantity = int(quantity_str)
        if quantity < 0:
            return "Quantity cannot be negative", 400

        parsed_date = None
        if use_by_date:
            try:
                parsed_date = pd.to_datetime(use_by_date).date()
            except ValueError:
                return "Invalid date format", 400

        df = pd.read_excel(PRODUCTS_FILE)
        exists = ((df['Item Name'].str.lower() == item_name.lower()) &
                  (df['Category'].str.lower() == category.lower())).any()
        if exists:
            return "Product already exists in this category.", 400

        new_row = {
            'Category': category,
            'Item Name': item_name,
            'Quantity': quantity,
            'Initial Quantity': quantity,
            'Image URL': image_url,
        }
        if parsed_date:
            new_row['Use By Date'] = parsed_date

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_excel(PRODUCTS_FILE, index=False)

        return redirect(url_for('category_view', category=category.lower()))

    return render_template('add_product.html')

@app.route('/delete-product', methods=['POST'])
def delete_product():
    if session.get("role") != "admin":
        return redirect(url_for('login'))  # or show unauthorized message

    product = request.form['product']
    category = request.form['category']

    # Load, filter out the deleted item, and save updated data
    df = pd.read_excel(PRODUCTS_FILE)
    df = df[~((df['Item Name'] == product) & (df['Category'] == category))]
    df.to_excel(PRODUCTS_FILE, index=False)

    return redirect(url_for('category_view', category=category.lower()))

@app.route('/update-quantity', methods=['POST'])
def update_quantity():
    if 'username' not in session:
        return redirect(url_for('login'))

    product = request.form['product']
    category = request.form['category']
    new_qty = request.form['new_quantity'].strip()

    if not new_qty.isdigit():
        return "Invalid quantity", 400

    new_qty = int(new_qty)
    df = pd.read_excel(PRODUCTS_FILE)
    mask = (df['Item Name'] == product) & (df['Category'].str.lower() == category.lower())

    if not mask.any():
        return f"Product '{product}' in category '{category}' not found.", 404

    df.loc[mask, 'Quantity'] = new_qty
    df.to_excel(PRODUCTS_FILE, index=False)

    return redirect(f"/{category.lower()}")

@app.route('/usage-trends')
def usage_trends():
    df = pd.read_excel(PRODUCTS_FILE)  # ✅ Corrected path

    df.columns = df.columns.str.strip()
    df['Category'] = df['Category'].str.strip()

    category_data = df.groupby('Category')['Quantity'].sum().reset_index()

    trends = []
    for category in df['Category'].unique():
        items = df[df['Category'] == category]
        trend = {
            'name': category,
            'labels': items['Item Name'].tolist(),
            'values': items['Quantity'].tolist()
        }
        trends.append(trend)

    category_summary = {
        'name': 'Category-wise Quantity',
        'labels': category_data['Category'].tolist(),
        'values': category_data['Quantity'].tolist()
    }

    return render_template('usage_trends.html', trends=trends, category_summary=category_summary)

@app.route('/settings')
def settings():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('settings.html', username=session['username'], role=session['role'])

# ---------------------- Run App ----------------------

if __name__ == '__main__':
    app.run(debug=True)
