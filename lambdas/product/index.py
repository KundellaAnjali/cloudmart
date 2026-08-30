import json
import boto3
import pymysql

ssm = boto3.client("ssm")


def get_parameter(name, decrypt=False):
    response = ssm.get_parameter(
        Name=name,
        WithDecryption=decrypt
    )
    return response["Parameter"]["Value"]


def get_connection():

    print("Lambda started")

    db_host = get_parameter("/cloudmart/dev/db/host")
    print("Got DB Host")

    db_name = get_parameter("/cloudmart/dev/db/name")
    print("Got DB Name")

    db_user = get_parameter("/cloudmart/dev/db/username")
    print("Got DB User")

    db_password = get_parameter(
        "/cloudmart/dev/db/password",
        decrypt=False
    )
    print("Got DB Password")

    print("Connecting to database...")

    connection = pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name,
        connect_timeout=10
    )

    print("Connected to database")

    return pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor
    )


def handler(event, context):

    try:

        connection = get_connection()

        with connection.cursor() as cursor:

            # Create table automatically
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

            # Insert sample records only once
            cursor.execute(
                "SELECT COUNT(*) AS total FROM product"
            )

            result = cursor.fetchone()

            if result["total"] == 0:

                cursor.execute("""
                INSERT INTO product
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
                    'High-performance laptop',
                    'Electronics',
                    75000.00,
                    10,
                    TRUE
                ),
                (
                    'Mouse',
                    'Wireless Mouse',
                    'Accessories',
                    500.00,
                    50,
                    TRUE
                ),
                (
                    'Keyboard',
                    'Mechanical Keyboard',
                    'Accessories',
                    1500.00,
                    25,
                    TRUE
                )
                """)

            connection.commit()

            cursor.execute("""
            SELECT
                product_id,
                product_name,
                description,
                category,
                price,
                stock_count,
                created_at,
                updated_at,
                is_active
            FROM product
            """)

            products = cursor.fetchall()

        connection.close()

        return {
            "statusCode": 200,
            "body": json.dumps(products, default=str)
        }

    except Exception as e:

        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e)
            })
        }