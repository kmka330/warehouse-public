-- 1. TABLES
-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) CHECK (role IN ('admin', 'warehouse', 'sales')) NOT NULL
);

-- Suppliers table
CREATE TABLE suppliers (
    id SERIAL PRIMARY KEY,
    company_name VARCHAR(100) NOT NULL,
    email VARCHAR(100)
);

-- Products table
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    sku VARCHAR(50) UNIQUE NOT NULL,
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL DEFAULT 0,
    supplier_id INTEGER REFERENCES suppliers(id)
);

-- Orders table
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    client_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'NEW' CHECK (status IN ('NEW', 'SHIPPED')),
    created_by INTEGER REFERENCES users(id)
);

-- Order Items table
CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

-- Price History table
CREATE TABLE price_history (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    old_price DECIMAL(10, 2),
    new_price DECIMAL(10, 2),
    change_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- 2. TRIGGERS
-- Update stock level
CREATE OR REPLACE FUNCTION update_stock_level()
RETURNS TRIGGER AS $$
DECLARE
    current_stock INTEGER;
BEGIN
    SELECT stock INTO current_stock FROM products WHERE id = NEW.product_id;
    
    IF current_stock < NEW.quantity THEN
        RAISE EXCEPTION 'Not enough stock';
    END IF;
    
    UPDATE products 
    SET stock = stock - NEW.quantity 
    WHERE id = NEW.product_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_stock
BEFORE INSERT ON order_items
FOR EACH ROW
EXECUTE FUNCTION update_stock_level();


-- Log price changes
CREATE OR REPLACE FUNCTION log_price_change()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.price <> NEW.price THEN
        INSERT INTO price_history (product_id, old_price, new_price, change_date)
        VALUES (NEW.id, OLD.price, NEW.price, CURRENT_TIMESTAMP);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_log_price_change
BEFORE UPDATE ON products
FOR EACH ROW
EXECUTE FUNCTION log_price_change();


-- 3. VIEWS
-- View order summary
CREATE OR REPLACE VIEW v_order_summary AS
SELECT 
    o.id AS order_id,
    o.date,
    o.client_name,
    SUM(oi.quantity * p.price) AS total_value
FROM orders o
JOIN order_items oi ON o.id = oi.order_id
JOIN products p ON oi.product_id = p.id
GROUP BY o.id, o.date, o.client_name;

-- View bestsellers
CREATE OR REPLACE VIEW v_bestsellers AS
SELECT 
    p.name,
    SUM(oi.quantity) AS total_sold
FROM order_items oi
JOIN products p ON oi.product_id = p.id
GROUP BY p.id, p.name
HAVING SUM(oi.quantity) > 10;

-- View supplier inventory value
CREATE OR REPLACE VIEW v_supplier_inventory AS
SELECT 
    s.company_name,
    COUNT(p.id) as products_count,
    SUM(p.stock * p.price) as total_inventory_value
FROM suppliers s
JOIN products p ON s.id = p.supplier_id
GROUP BY s.id, s.company_name
ORDER BY total_inventory_value DESC;

-- View sales by employee
CREATE OR REPLACE VIEW v_sales_by_employee AS
SELECT 
    u.username,
    COUNT(DISTINCT o.id) as orders_count,
    COALESCE(SUM(oi.quantity * p.price), 0) as total_sales_value
FROM users u
JOIN orders o ON u.id = o.created_by
JOIN order_items oi ON o.id = oi.order_id
JOIN products p ON oi.product_id = p.id
GROUP BY u.id, u.username
ORDER BY total_sales_value DESC;

-- View low stock
CREATE OR REPLACE VIEW v_low_stock AS
SELECT 
    name,
    sku,
    stock,
    price,
    (SELECT company_name FROM suppliers WHERE id = products.supplier_id) as supplier_name
FROM products
WHERE stock < 10
ORDER BY stock ASC;

-- View worst sellers
CREATE OR REPLACE VIEW v_worst_sellers AS
SELECT 
    p.name,
    p.sku,
    p.price,
    p.stock,
    COALESCE(SUM(oi.quantity), 0) as total_sold
FROM products p
LEFT JOIN order_items oi ON p.id = oi.product_id
GROUP BY p.id, p.name, p.sku, p.price, p.stock
HAVING COALESCE(SUM(oi.quantity), 0) <= 10
ORDER BY total_sold ASC
LIMIT 10;


-- 4. SEED DATA
-- Users
-- Passwords were hashed using PBKDF2 with SHA256 once for testing purposes
-- $algorithm$iterations$salt$hash
-- For new users passwords are hashed by server application
INSERT INTO users (username, password_hash, role) VALUES
('admin', 'pbkdf2:sha256:1000000$HoGUL1LAxU1eVolQ$c14b5d990776badd8387b603efebeb59899ff847accb58ce43e2ddca3bd0af69', 'admin'),
('magazynier', 'pbkdf2:sha256:1000000$d5cLzMIuoFS8PMk3$7ffbc40b277f9ccc86fbe14d71713cb6b50c8f203c6f09a9190c270cd0d7a494', 'warehouse'),
('sprzedawca', 'pbkdf2:sha256:1000000$d5cLzMIuoFS8PMk3$7ffbc40b277f9ccc86fbe14d71713cb6b50c8f203c6f09a9190c270cd0d7a494', 'sales');

-- Suppliers
INSERT INTO suppliers (company_name, email) VALUES
('Dostawca A', 'kontakt@dostawca-a.pl'),
('Hurtownia B', 'biuro@hurtownia-b.com'),
('Import C', 'sales@import-c.eu');

-- Products
INSERT INTO products (name, sku, price, stock, supplier_id) VALUES
('Laptop Dell', 'DELL-001', 3500.00, 50, 1),
('Mysz Logitech', 'LOGI-002', 150.00, 200, 1),
('Monitor Samsung', 'SAMS-003', 1200.00, 30, 2),
('Klawiatura Mech', 'MECH-004', 450.00, 15, 2),
('Kabel HDMI', 'HDMI-005', 25.00, 500, 3);

INSERT INTO orders (client_name, created_by) VALUES ('Klient Testowy 1', 3);
INSERT INTO order_items (order_id, product_id, quantity) VALUES (1, 2, 5);

INSERT INTO orders (client_name, created_by) VALUES ('Firma XYZ', 3);
INSERT INTO order_items (order_id, product_id, quantity) VALUES (2, 5, 20);

INSERT INTO orders (client_name, created_by) VALUES ('Jan Kowalski', 3);
INSERT INTO order_items (order_id, product_id, quantity) VALUES (3, 1, 1);
