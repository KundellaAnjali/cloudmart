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

ENVIRONMENT = os.environ["ENVIRONMENT"]
def get_parameter(name, decrypt=False):
    try:
        response = ssm.get_parameter(
            Name=name,
            WithDecryption=decrypt
        )

        return response["Parameter"]["Value"]

    except Exception:
        publish_metric("ParameterAccessFailures")
        raise

STOCK_THRESHOLD = int(
    get_parameter(
        f"/cloudmart/{ENVIRONMENT}/inventory/stock-threshold"
    )
)

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

def send_stock_alert(product_id, product_name, stock_count):

    detail_type = (
        "OutOfStock"
        if stock_count == 0
        else "LowStock"
    )

    events.put_events(
        Entries=[
            {
                "Source": "cloudmart.inventory",
                "DetailType": detail_type,
                "Detail": json.dumps({
                    "subject": (
                        "CloudMart Out Of Stock Alert"
                        if stock_count == 0
                        else "CloudMart Low Stock Alert"
                    ),
                    "message": (
                        f"Product {product_name} is out of stock."
                        if stock_count == 0
                        else f"Product {product_name} has low stock. Current stock: {stock_count}"
                    )
                })
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
        publish_metric("ProductNotFound")
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

    
    threshold = STOCK_THRESHOLD
    stock_count = body["stock_count"]

    if stock_count < 0:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "message": "Stock count cannot be negative"
            })
        }

    try:

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

        if stock_count == 0:

            send_stock_alert(
                product_id,
                body["product_name"],
                stock_count
            )

            publish_metric("OutOfStockProducts")

        elif 0 < stock_count < STOCK_THRESHOLD:

            send_stock_alert(
                product_id,
                body["product_name"],
                stock_count
            )

            publish_metric("LowStockProducts")

    except Exception as e:

        connection.rollback()

        publish_metric("ProductCreationFailures")

        logger.error(json.dumps({
            "level": "ERROR",
            "operation": "CreateProduct",
            "message": "Product creation failed",
            "error": repr(e)
        }))

        raise
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

        threshold = STOCK_THRESHOLD
        if body["stock_count"] < 0:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "message": "Stock count cannot be negative"
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

    if "stock_count" in body:

        stock_count = body["stock_count"]
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT product_name
                FROM product
                WHERE product_id = %s
            """, (product_id,))
            
            product = cursor.fetchone()

        product_name = product["product_name"]

        if stock_count == 0:

            send_stock_alert(
                product_id,
                product_name,
                stock_count
            )

            publish_metric("OutOfStockProducts")

        elif 0 < stock_count < STOCK_THRESHOLD:

            send_stock_alert(
                product_id,
                product_name,
                stock_count
            )

            publish_metric("LowStockProducts")



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
    #raise Exception("Test 5XX")
    try:

        try:
            connection = get_connection()
        except Exception as e:

            publish_metric("RDSConnectionFailures")

            logger.error(json.dumps({
                "level": "ERROR",
                "operation": "DatabaseConnection",
                "message": "Failed to connect to database",
                "error": str(e)
            }))

            raise


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
        publish_metric("ProductLambdaFailures")
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
    
    