```python
import boto3
import pymysql
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ssm = boto3.client("ssm")
cloudwatch = boto3.client("cloudwatch")

ENVIRONMENT = os.environ["ENVIRONMENT"]


def publish_metric(metric_name, value=1):
    """Publish a custom CloudWatch metric."""
    try:
        cloudwatch.put_metric_data(
            Namespace="CloudMart",
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Value": value,
                    "Unit": "Count"
                }
            ]
        )

        logger.info(
            f"Published metric: {metric_name} = {value}"
        )

    except Exception as e:
        logger.error(
            f"Failed to publish metric {metric_name}: {str(e)}"
        )


def get_parameter(name, decrypt=False):
    try:
        response = ssm.get_parameter(
            Name=name,
            WithDecryption=decrypt
        )

        return response["Parameter"]["Value"]

    except Exception as e:
        logger.error(
            f"Failed to access SSM parameter {name}: {str(e)}"
        )

        publish_metric("ParameterAccessFailures")

        raise


def get_connection():
    logger.info("Creating database connection")

    db_host = get_parameter(
        f"/cloudmart/{ENVIRONMENT}/db/host"
    )

    db_name = get_parameter(
        f"/cloudmart/{ENVIRONMENT}/db/name"
    )

    db_user = get_parameter(
        f"/cloudmart/{ENVIRONMENT}/db/username"
    )

    db_password = get_parameter(
        f"/cloudmart/{ENVIRONMENT}/db/password",
        decrypt=True
    )

    logger.info(
        f"Connecting to database {db_name}"
    )

    return pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor
    )


def handler(event, context):

    logger.info("Schema initialization started")

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            # =========================================================
            # CUSTOMERS TABLE
            # =========================================================

            logger.info("Creating customers table")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id INT AUTO_INCREMENT PRIMARY KEY,
                    customer_name VARCHAR(100) NOT NULL,
                    customer_email VARCHAR(255) NOT NULL UNIQUE,
                    auth_token VARCHAR(255),
                    role VARCHAR(20) DEFAULT 'CUSTOMER',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP
                )
            """)

            logger.info("Customers table ready")


            # =========================================================
            # PRODUCT TABLE
            # =========================================================

            logger.info("Creating product table")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS product (
                    product_id INT AUTO_INCREMENT PRIMARY KEY,
                    product_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    category VARCHAR(100),
                    price DECIMAL(10,2) NOT NULL,
                    stock_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)

            logger.info("Product table ready")


            # =========================================================
            # ORDERS TABLE
            # =========================================================

            logger.info("Creating orders table")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id VARCHAR(50) PRIMARY KEY,
                    customer_id INT NOT NULL,
                    order_status VARCHAR(30) DEFAULT 'PENDING',
                    total_amount DECIMAL(10,2) NOT NULL,
                    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id)
                    REFERENCES customers(customer_id)
                )
            """)

            logger.info("Orders table ready")


            # =========================================================
            # ORDER ITEMS TABLE
            # =========================================================

            logger.info("Creating order_items table")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    order_item_id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(50) NOT NULL,
                    product_id INT NOT NULL,
                    product_name VARCHAR(255),
                    quantity INT NOT NULL,
                    unit_price DECIMAL(10,2) NOT NULL,
                    FOREIGN KEY (order_id)
                    REFERENCES orders(order_id),
                    FOREIGN KEY (product_id)
                    REFERENCES product(product_id)
                )
            """)

            logger.info("Order items table ready")


            # =========================================================
            # ORDER STATUS HISTORY TABLE
            # =========================================================

            logger.info("Creating order_status_history table")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS order_status_history (
                    status_history_id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(50) NOT NULL,
                    order_status VARCHAR(30) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    archived_at TIMESTAMP NULL,
                    remarks VARCHAR(255),
                    FOREIGN KEY (order_id)
                    REFERENCES orders(order_id)
                )
            """)

            logger.info("Order status history table ready")


            # =========================================================
            # SAMPLE USERS
            # =========================================================

            logger.info("Inserting sample users")

            cursor.execute("""
                INSERT IGNORE INTO customers
                (
                    customer_name,
                    customer_email,
                    auth_token,
                    role,
                    is_active
                )
                VALUES
                (
                    'Admin User',
                    'kundella.anjali@omc.com',
                    'admin123token',
                    'ADMIN',
                    TRUE
                )
            """)

            cursor.execute("""
                INSERT IGNORE INTO customers
                (
                    customer_name,
                    customer_email,
                    auth_token,
                    role,
                    is_active
                )
                VALUES
                (
                    'Product Manager',
                    'kundelakomala@gmail.com',
                    'product123token',
                    'PRODUCT',
                    TRUE
                )
            """)

            cursor.execute("""
                INSERT IGNORE INTO customers
                (
                    customer_name,
                    customer_email,
                    auth_token,
                    role,
                    is_active
                )
                VALUES
                (
                    'Customer One',
                    'kundellaanjali2004@gmail.com',
                    'customer123token',
                    'CUSTOMER',
                    TRUE
                )
            """)

            cursor.execute("""
                INSERT IGNORE INTO customers
                (
                    customer_name,
                    customer_email,
                    auth_token,
                    role,
                    is_active
                )
                VALUES
                (
                    'Customer Two',
                    'customer2@cloudmart.com',
                    'customer456token',
                    'CUSTOMER',
                    TRUE
                )
            """)

            cursor.execute("""
                INSERT IGNORE INTO customers
                (
                    customer_name,
                    customer_email,
                    auth_token,
                    role,
                    is_active
                )
                VALUES
                (
                    'Customer Three',
                    'customer3@cloudmart.com',
                    'customer789token',
                    'CUSTOMER',
                    TRUE
                )
            """)

            logger.info("Sample users inserted successfully")


            # =========================================================
            # SAMPLE PRODUCTS
            # =========================================================

            logger.info("Inserting sample products")

            cursor.execute("""
                INSERT IGNORE INTO product
                (
                    product_name,
                    description,
                    category,
                    price,
                    stock_count,
                    is_active
                )
                VALUES
                (
                    'Laptop',
                    'Dell Inspiron 15 Laptop',
                    'Electronics',
                    55000.00,
                    50,
                    TRUE
                )
            """)

            cursor.execute("""
                INSERT IGNORE INTO product
                (
                    product_name,
                    description,
                    category,
                    price,
                    stock_count,
                    is_active
                )
                VALUES
                (
                    'Wireless Mouse',
                    'Logitech Wireless Mouse',
                    'Accessories',
                    799.00,
                    100,
                    TRUE
                )
            """)

            cursor.execute("""
                INSERT IGNORE INTO product
                (
                    product_name,
                    description,
                    category,
                    price,
                    stock_count,
                    is_active
                )
                VALUES
                (
                    'Mechanical Keyboard',
                    'RGB Mechanical Keyboard',
                    'Accessories',
                    2499.00,
                    75,
                    TRUE
                )
            """)

            cursor.execute("""
                INSERT IGNORE INTO product
                (
                    product_name,
                    description,
                    category,
                    price,
                    stock_count,
                    is_active
                )
                VALUES
                (
                    'Monitor',
                    '24 Inch Full HD Monitor',
                    'Electronics',
                    8999.00,
                    40,
                    TRUE
                )
            """)

            cursor.execute("""
                INSERT IGNORE INTO product
                (
                    product_name,
                    description,
                    category,
                    price,
                    stock_count,
                    is_active
                )
                VALUES
                (
                    'USB-C Charger',
                    '65W Fast Charging Adapter',
                    'Accessories',
                    1499.00,
                    60,
                    TRUE
                )
            """)

            logger.info("Sample products inserted successfully")


            # =========================================================
            # ORDER 1
            # =========================================================

            cursor.execute("""
                INSERT IGNORE INTO orders
                (
                    order_id,
                    customer_id,
                    order_status,
                    total_amount
                )
                VALUES
                (
                    'ORD-100001',
                    3,
                    'CONFIRMED',
                    55799.00
                )
            """)

            cursor.execute("""
                INSERT INTO order_items
                (
                    order_id,
                    product_id,
                    product_name,
                    quantity,
                    unit_price
                )
                VALUES
                    (
                        'ORD-100001',
                        1,
                        'Laptop',
                        1,
                        55000.00
                    ),
                    (
                        'ORD-100001',
                        2,
                        'Wireless Mouse',
                        1,
                        799.00
                    )
            """)

            cursor.execute("""
                INSERT INTO order_status_history
                (
                    order_id,
                    order_status,
                    remarks
                )
                VALUES
                    (
                        'ORD-100001',
                        'PENDING',
                        'Order created'
                    ),
                    (
                        'ORD-100001',
                        'CONFIRMED',
                        'Inventory deducted'
                    )
            """)


            # =========================================================
            # ORDER 2
            # =========================================================

            cursor.execute("""
                INSERT IGNORE INTO orders
                (
                    order_id,
                    customer_id,
                    order_status,
                    total_amount
                )
                VALUES
                (
                    'ORD-100002',
                    4,
                    'CONFIRMED',
                    11498.00
                )
            """)

            cursor.execute("""
                INSERT INTO order_items
                (
                    order_id,
                    product_id,
                    product_name,
                    quantity,
                    unit_price
                )
                VALUES
                    (
                        'ORD-100002',
                        4,
                        'Monitor',
                        1,
                        8999.00
                    ),
                    (
                        'ORD-100002',
                        5,
                        'USB-C Charger',
                        1,
                        1499.00
                    ),
                    (
                        'ORD-100002',
                        3,
                        'Mechanical Keyboard',
                        1,
                        1000.00
                    )
            """)

            cursor.execute("""
                INSERT INTO order_status_history
                (
                    order_id,
                    order_status,
                    remarks
                )
                VALUES
                    (
                        'ORD-100002',
                        'PENDING',
                        'Order created'
                    ),
                    (
                        'ORD-100002',
                        'CONFIRMED',
                        'Inventory deducted'
                    )
            """)


            # =========================================================
            # ORDER 3
            # =========================================================

            cursor.execute("""
                INSERT IGNORE INTO orders
                (
                    order_id,
                    customer_id,
                    order_status,
                    total_amount
                )
                VALUES
                (
                    'ORD-100003',
                    5,
                    'CANCELLED',
                    3997.00
                )
            """)

            cursor.execute("""
                INSERT INTO order_items
                (
                    order_id,
                    product_id,
                    product_name,
                    quantity,
                    unit_price
                )
                VALUES
                    (
                        'ORD-100003',
                        2,
                        'Wireless Mouse',
                        2,
                        799.00
                    ),
                    (
                        'ORD-100003',
                        5,
                        'USB-C Charger',
                        1,
                        1499.00
                    ),
                    (
                        'ORD-100003',
                        3,
                        'Mechanical Keyboard',
                        1,
                        900.00
                    )
            """)

            cursor.execute("""
                INSERT INTO order_status_history
                (
                    order_id,
                    order_status,
                    remarks
                )
                VALUES
                    (
                        'ORD-100003',
                        'PENDING',
                        'Order created'
                    ),
                    (
                        'ORD-100003',
                        'CONFIRMED',
                        'Inventory deducted'
                    ),
                    (
                        'ORD-100003',
                        'CANCELLED',
                        'Order cancelled'
                    )
            """)


        # =============================================================
        # COMMIT
        # =============================================================

        conn.commit()

        logger.info(
            "Database schema created successfully"
        )

        return {
            "statusCode": 200,
            "body": "Schema initialized successfully"
        }


    except Exception as e:

        logger.error(
            f"Schema initialization failed: {str(e)}"
        )

        # Publish SchemaInitErrors metric
        publish_metric("SchemaInitErrors")

        # Roll back all database changes
        conn.rollback()

        raise


    finally:

        logger.info(
            "Closing database connection"
        )

        conn.close()