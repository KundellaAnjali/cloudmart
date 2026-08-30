import json
import boto3
import pymysql

ssm = boto3.client("ssm")
sns = boto3.client("sns")
events = boto3.client("events")

def get_parameter(name, decrypt=False):
    response = ssm.get_parameter(
        Name=name,
        WithDecryption=decrypt
    )
    return response["Parameter"]["Value"]


def get_connection():

    print("Lambda started")

    db_host = get_parameter("/cloudmart/dev/db/host")
    

    db_name = get_parameter("/cloudmart/dev/db/name")
    

    db_user = get_parameter("/cloudmart/dev/db/username")
    

    db_password = get_parameter(
        "/cloudmart/dev/db/password",
        decrypt=False
    )
    

    print("Connecting to database...")

    connection = pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name,
        connect_timeout=10,
        cursorclass=pymysql.cursors.DictCursor
    )

    print("Connected to database")

    return connection

def get_all_products(connection):

    with connection.cursor() as cursor:

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

    return {
        "statusCode": 200,
        "body": json.dumps(products, default=str)
    }


def get_product_by_id(connection, product_id):

    with connection.cursor() as cursor:

        cursor.execute("""
            SELECT *
            FROM product
            WHERE product_id = %s
        """, (product_id,))

        product = cursor.fetchone()

    return {
        "statusCode": 200,
        "body": json.dumps(product, default=str)
    }


def create_product(connection, event):

    body = json.loads(event["body"])

    with connection.cursor() as cursor:

        cursor.execute("""
            INSERT INTO product (
                product_name,
                description,
                category,
                price,
                stock_count,
                is_active
            )
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            body["product_name"],
            body["description"],
            body["category"],
            body["price"],
            body["stock_count"],
            True
        ))

    connection.commit()

    return {
        "statusCode": 201,
        "body": json.dumps({
            "message": "Product created successfully"
        })
    }

def update_product(connection, product_id, event):

    body = json.loads(event["body"])

    with connection.cursor() as cursor:

        cursor.execute("""
            UPDATE product
            SET
                product_name=%s,
                description=%s,
                category=%s,
                price=%s,
                stock_count=%s
            WHERE product_id=%s
        """, (
            body["product_name"],
            body["description"],
            body["category"],
            body["price"],
            body["stock_count"],
            product_id
        ))

    connection.commit()
    print("Before eventbridge")
    events.put_events(
        Entries=[
            {
                "Source": "cloudmart.inventory",
                "DetailType": "InventoryUpdated",
                "Detail": json.dumps({
                    "product_id": product_id,
                    "product_name": body["product_name"],
                    "stock_count": body["stock_count"]
                })
            }
        ]
    )
    print("After eventbridge")

    with connection.cursor() as cursor:

        threshold = int(
            get_parameter("/cloudmart/dev/inventory/stock-threshold")
        )

        cursor.execute("""
            SELECT product_name, stock_count
            FROM product
            WHERE product_id = %s
        """, (product_id,))

        product = cursor.fetchone()

        if product["stock_count"] < threshold:
            print("before sns")
            sns.publish(
                TopicArn=get_parameter("/cloudmart/dev/sns/topic-arn"),
                Subject="Low Stock Alert",
                Message=f"""
            print("after sns")
Product: {product['product_name']}
Current Stock: {product['stock_count']}
Threshold: {threshold}
"""
            )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Product updated successfully"
        })
    }

def delete_product(connection, product_id):

    with connection.cursor() as cursor:

        cursor.execute("""
            DELETE FROM product
            WHERE product_id=%s
        """, (product_id,))

    connection.commit()

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Product deleted successfully"
        })
    }
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

        http_method = event.get("httpMethod")
        path_parameters = event.get("pathParameters") or {}

        if http_method == "GET" and path_parameters.get("id"):
            response = get_product_by_id(
                connection,
                path_parameters["id"]
            )

        elif http_method == "GET":
            response = get_all_products(connection)

        elif http_method == "POST":
            response = create_product(
                connection,
                event
            )

        elif http_method == "PUT":
            response = update_product(
                connection,
                path_parameters["id"],
                event
            )

        elif http_method == "DELETE":
            response = delete_product(
                connection,
                path_parameters["id"]
            )

        else:
            response = {
                "statusCode": 405,
                "body": json.dumps({
                    "message": "Method not allowed"
                })
            }

        connection.close()

        return response

    except Exception as e:

        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e)
            })
        }