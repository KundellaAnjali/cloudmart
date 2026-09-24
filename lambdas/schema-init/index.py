import boto3
import pymysql
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ssm = boto3.client("ssm")

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")


def get_parameter(name, decrypt=False):
    logger.info(f"Fetching parameter: {name}")

    response = ssm.get_parameter(
        Name=name,
        WithDecryption=decrypt
    )

    return response["Parameter"]["Value"]


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

        raise

    finally:

        logger.info("Closing database connection")

        conn.close()