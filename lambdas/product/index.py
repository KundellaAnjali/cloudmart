import json
import boto3
import pymysql
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ssm = boto3.client("ssm")
events = boto3.client("events")
cloudwatch = boto3.client("cloudwatch")

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")


def get_parameter(name, decrypt=False):
    response = ssm.get_parameter(
        Name=name,
        WithDecryption=decrypt
    )
    return response["Parameter"]["Value"]


def get_connection():

    logger.info("Lambda started")


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

    logger.info("Connecting to database")

    connection = pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name,
        connect_timeout=10,
        cursorclass=pymysql.cursors.DictCursor
    )

    logger.info(json.dumps({
        "level": "INFO",
        "operation": "DatabaseConnection",
        "message": "Connected to database"
    }))

    return connection

def publish_metric(metric_name, value=1):

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
            WHERE is_active = TRUE
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
            AND is_active = TRUE
        """, (product_id,))

        product = cursor.fetchone()

    if product is None:
        logger.warning(json.dumps({
            "level": "WARNING",
            "operation": "GetProductById",
            "message": "Product not found",
            "product_id": product_id
        }))
        return {
            "statusCode": 404,
            "body": json.dumps({
                "message": "Product not found"
            })
        }

    return {
        "statusCode": 200,
        "body": json.dumps(product, default=str)
    }


def create_product(connection, event):
    body = json.loads(event["body"])

    logger.info(json.dumps({
        "level": "INFO",
        "operation": "CreateProduct",
        "message": "Create product request received",
        "product_name": body.get("product_name"),
        "category": body.get("category")
    }))

    
    threshold = int(
        get_parameter(
            f"/cloudmart/{ENVIRONMENT}/inventory/stock-threshold"
        )
    )
    stock_count = body["stock_count"]

    if stock_count < 0:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "message": "Stock count cannot be negative"
            })
        }

    if stock_count < threshold:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "message": f"Stock count cannot be less than threshold value ({threshold})"
            })
        }

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

        product_id = cursor.lastrowid
        logger.info(json.dumps({
            "level": "INFO",
            "operation": "CreateProduct",
            "message": "Product created successfully",
            "product_id": product_id
        }))

    connection.commit()
    publish_metric("ProductsCreated")
    return {
        "statusCode": 201,
        "body": json.dumps({
            "message": "Product created successfully",
            "product_id": product_id
        })
    }


def update_product(connection, product_id, event):

    body = json.loads(event["body"])

    allowed_fields = {
        "product_name": "product_name",
        "description": "description",
        "category": "category",
        "price": "price",
        "stock_count": "stock_count"
    }

    update_fields = []
    values = []

    for field in allowed_fields:
        if field in body:
            update_fields.append(f"{allowed_fields[field]} = %s")
            values.append(body[field])

    if not update_fields:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "message": "No fields provided for update"
            })
        }

    if "stock_count" in body:

        threshold = int(
            get_parameter(
                f"/cloudmart/{ENVIRONMENT}/inventory/stock-threshold"
            )
        )

        if body["stock_count"] < 0:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "message": "Stock count cannot be negative"
                })
            }

        if body["stock_count"] < threshold:
            
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "message": f"Stock count must be greater than or equal to threshold value ({threshold})"
                })
            }

    values.append(product_id)

    query = f"""
        UPDATE product
        SET {', '.join(update_fields)}
        WHERE product_id = %s
        AND is_active = TRUE
    """

    with connection.cursor() as cursor:

        cursor.execute(query, values)

        if cursor.rowcount == 0:
            return {
                "statusCode": 404,
                "body": json.dumps({
                    "message": "Product not found"
                })
            }

    connection.commit()
    publish_metric("InventoryUpdated")
    events.put_events(
        Entries=[
            {
                "Source": "cloudmart.inventory",
                "DetailType": "InventoryUpdated",
                "Detail": json.dumps({
                    "product_id": product_id,
                    "updated_fields": body
                })
            }
        ]
    )

    logger.info(json.dumps({
        "level": "INFO",
        "operation": "UpdateProduct",
        "message": "Product updated successfully",
        "product_id": product_id,
        "updated_fields": body
    }))

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Product updated successfully",
            "product_id": product_id
        })
    }

def delete_product(connection, product_id):

    with connection.cursor() as cursor:

        cursor.execute("""
            UPDATE product
            SET is_active = FALSE
            WHERE product_id = %s
            AND is_active = TRUE
        """, (product_id,))

        if cursor.rowcount == 0:
            logger.warning(json.dumps({
                "level": "WARNING",
                "operation": "DeleteProduct",
                "message": "Product not found",
                "product_id": product_id
            }))

            return {
                "statusCode": 404,
                "body": json.dumps({
                    "message": "Product not found"
                })
            }

    connection.commit()

    logger.info(json.dumps({
        "level": "INFO",
        "operation": "DeleteProduct",
        "message": "Product deleted successfully",
        "product_id": product_id
    }))

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Product soft deleted successfully",
            "product_id": product_id
        })
    }


def handler(event, context):

    try:

        connection = get_connection()

        with connection.cursor() as cursor:

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

        elif http_method == "PATCH":

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

        logger.error(json.dumps({
            "level": "ERROR",
            "operation": "ProductLambda",
            "error": repr(e)
        }))

        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": repr(e)
            })
        }
    
    