import json
import uuid
import pymysql
import boto3
import os

ssm = boto3.client("ssm")
events = boto3.client("events")

DB_HOST = ssm.get_parameter(
    Name="/cloudmart/dev/db/host"
)["Parameter"]["Value"]

DB_NAME = ssm.get_parameter(
    Name="/cloudmart/dev/db/name"
)["Parameter"]["Value"]

DB_USER = ssm.get_parameter(
    Name="/cloudmart/dev/db/username"
)["Parameter"]["Value"]

DB_PASSWORD = ssm.get_parameter(
    Name="/cloudmart/dev/db/password",
    WithDecryption=True
)["Parameter"]["Value"]

def initialize_schema():

    conn = get_connection()

    try:

        schema_file = os.path.join(
            os.path.dirname(__file__),
            "schema.sql"
        )

        with open(schema_file, "r") as f:
            sql_script = f.read()

        with conn.cursor() as cursor:

            for statement in sql_script.split(";"):

                statement = statement.strip()

                if statement:
                    cursor.execute(statement)

        conn.commit()

    finally:
        conn.close()

print("DB_HOST:", DB_HOST)
print("DB_NAME:", DB_NAME)
def get_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

def response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps(body, default=str)
    }

def publish_event(detail_type, detail, source="cloudmart.orders"):
    events.put_events(
        Entries=[
            {
                "Source": source,
                "DetailType": detail_type,
                "Detail": json.dumps(detail)
            }
        ]
    )
def create_customer(event):

    body = json.loads(event.get("body", "{}"))

    customer_name = body.get("customerName")
    customer_email = body.get("customerEmail")

    if not customer_name:
        return response(
            400,
            {"message": "customerName is required"}
        )

    if not customer_email:
        return response(
            400,
            {"message": "customerEmail is required"}
        )

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO customers
                (
                    customer_name,
                    customer_email
                )
                VALUES
                (%s,%s)
                """,
                (
                    customer_name,
                    customer_email
                )
            )

            customer_id = cursor.lastrowid

            conn.commit()

            return response(
                201,
                {
                    "message": "Customer created successfully",
                    "customerId": customer_id
                }
            )
            

    except Exception as e:

        conn.rollback()

        return response(
            500,
            {
                "message": str(e)
            }
        )

    finally:
        conn.close()

def get_customers():

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM customers
                ORDER BY customer_id
                """
            )

            customers = cursor.fetchall()

            return response(200, customers)

    except Exception as e:

        return response(
            500,
            {
                "message": str(e)
            }
        )

    finally:
        conn.close()

def get_customer_by_id(customer_id):

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM customers
                WHERE customer_id = %s
                """,
                (customer_id,)
            )

            customer = cursor.fetchone()

            if not customer:
                return response(
                    404,
                    {
                        "message": "Customer not found"
                    }
                )

            return response(
                200,
                customer
            )

    except Exception as e:

        return response(
            500,
            {
                "message": str(e)
            }
        )

    finally:
        conn.close()

def create_order(event):

    body = json.loads(event.get("body", "{}"))

    customer_id = body.get("customerId")
    items = body.get("items", [])

    if not customer_id:
        return response(400, {"message": "customerId is required"})

    if not items:
        return response(400, {"message": "items are required"})

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute("SELECT DATABASE() AS db")
            print("DATABASE:", cursor.fetchone())

            cursor.execute("SHOW TABLES")
            print("TABLES:", cursor.fetchall())

            cursor.execute(
                """
                SELECT *
                FROM customers
                WHERE customer_id = %s
                """,
                (customer_id,)
            )

            customer = cursor.fetchone()

            if not customer:
                return response(
                    404,
                    {"message": "Customer not found"}
                )

            total_amount = 0
            product_details = []

            for item in items:

                product_id = item["productId"]
                quantity = item["quantity"]

                cursor.execute(
                    """
                    SELECT product_id,
                           product_name,
                           price,
                           stock_count
                    FROM product
                    WHERE product_id = %s
                    AND is_active = TRUE
                    """,
                    (product_id,)
                )

                product = cursor.fetchone()

                if not product:

                    publish_event(
                        "OrderFailed",
                        {
                            "customerId": customer_id,
                            "productId": product_id,
                            "reason": "Product not found"
                        }
                    )

                    return response(
                        404,
                        {
                            "message":
                            f"Product {product_id} not found"
                        }
                    )

                if quantity > product["stock_count"]:

                    publish_event(
                        "OrderFailed",
                        {
                            "customerId": customer_id,
                            "productId": product_id,
                            "availableStock": product["stock_count"],
                            "requestedQuantity": quantity,
                            "reason": "Insufficient stock"
                        }
                    )

                    return response(
                        400,
                        {
                            "message":
                            f"Insufficient stock for product {product_id}"
                        }
                    )

                total_amount += (
                    float(product["price"]) * quantity
                )

                product_details.append(
                    {
                        "product": product,
                        "quantity": quantity
                    }
                )

            order_id = f"ORD-{uuid.uuid4().hex[:8]}"

            cursor.execute(
                """
                INSERT INTO orders
                (
                    order_id,
                    customer_id,
                    order_status,
                    total_amount
                )
                VALUES
                (%s,%s,%s,%s)
                """,
                (
                    order_id,
                    customer_id,
                    "PENDING",
                    total_amount
                )
            )

            for item in product_details:

                product = item["product"]
                quantity = item["quantity"]
                cursor.execute(
                    """
                    UPDATE product
                    SET stock_count = stock_count - %s
                    WHERE product_id = %s
                    """,
                    (
                        quantity,
                        product["product_id"]
                    )
                )

                cursor.execute(
                    """
                    INSERT INTO order_items
                    (
                        order_id,
                        product_id,
                        product_name,
                        quantity,
                        unit_price
                    )
                    VALUES
                    (%s,%s,%s,%s,%s)
                    """,
                    (
                        order_id,
                        product["product_id"],
                        product["product_name"],
                        quantity,
                        product["price"]
                    )
                )

                cursor.execute(
                    """
                    SELECT product_name, stock_count
                    FROM product
                    WHERE product_id = %s
                    AND is_active = TRUE
                    """,
                    (product["product_id"],)
                )

                updated_product = cursor.fetchone()

                threshold = 10

                if updated_product["stock_count"] < threshold:

                    publish_event(
                        "LowStock",
                        {
                            "productId": product["product_id"],
                            "productName": product["product_name"],
                            "stockCount": updated_product["stock_count"],
                            "threshold": threshold
                        },

                        "cloudmart.inventory"
                    )

            cursor.execute(
                """
                INSERT INTO order_status_history
                (
                    order_id,
                    order_status,
                    remarks
                )
                VALUES
                (%s,%s,%s)
                """,
                (
                    order_id,
                    "PENDING",
                    "Order created"
                )
            )

            cursor.execute(
                """
                UPDATE orders
                SET order_status = %s
                WHERE order_id = %s
                """,
                (
                    "CONFIRMED",
                    order_id
                )
            )

            cursor.execute(
                """
                INSERT INTO order_status_history
                (
                    order_id,
                    order_status,
                    remarks
                )
                VALUES
                (%s,%s,%s)
                """,
                (
                    order_id,
                    "CONFIRMED",
                    "Inventory deducted"
                )
            )

            conn.commit()
            publish_event(
                "OrderPlaced",
                {
                    "orderId": order_id,
                    "customerId": customer_id,
                    "totalAmount": total_amount
                }
            )

            publish_event(
                "OrderConfirmed",
                {
                    "orderId": order_id,
                    "customerId": customer_id,
                    "totalAmount": total_amount,
                    "status": "CONFIRMED"
                }
            )

            return response(
                201,
                {
                    "orderId": order_id,
                    "productIds": [
                        item["product"]["product_id"]
                        for item in product_details
                    ],
                    "status": "CONFIRMED",
                    "totalAmount": total_amount
                }
            )

    except Exception as e:

        conn.rollback()

        print("ERROR:", str(e))

        return response(
            500,
            {
                "message": str(e)
            }
        )

    finally:
        conn.close()

def get_order(order_id):

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM orders
                WHERE order_id = %s
                """,
                (order_id,)
            )

            order = cursor.fetchone()

            if not order:
                return response(
                    404,
                    {
                        "message": "Order not found"
                    }
                )

            cursor.execute(
                """
                SELECT product_id,
                       product_name,
                       quantity,
                       unit_price
                FROM order_items
                WHERE order_id = %s
                """,
                (order_id,)
            )

            items = cursor.fetchall()

            order["items"] = items

            return response(200, order)

    except Exception as e:

        return response(
            500,
            {
                "message": str(e)
            }
        )

    finally:
        conn.close()

def get_customer_orders(customer_id):

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM orders
                WHERE customer_id = %s
                ORDER BY order_date DESC
                """,
                (customer_id,)
            )

            orders = cursor.fetchall()

            return response(200, orders)

    except Exception as e:

        return response(
            500,
            {
                "message": str(e)
            }
        )

    finally:
        conn.close()

def get_all_orders():

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM orders
                ORDER BY order_date DESC
                """
            )

            orders = cursor.fetchall()

            return response(200, orders)

    except Exception as e:

        return response(
            500,
            {
                "message": str(e)
            }
        )

    finally:
        conn.close()

def cancel_order(order_id):

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT order_status
                FROM orders
                WHERE order_id = %s
                """,
                (order_id,)
            )

            order = cursor.fetchone()

            if not order:
                return response(
                    404,
                    {
                        "message": "Order not found"
                    }
                )

            if order["order_status"] == "CANCELLED":
                return response(
                    400,
                    {
                        "message": "Order is already cancelled"
                    }
                )

            cursor.execute(
                """
                SELECT product_id,
                       quantity
                FROM order_items
                WHERE order_id = %s
                """,
                (order_id,)
            )

            items = cursor.fetchall()

            for item in items:

                cursor.execute(
                    """
                    UPDATE product
                    SET stock_count = stock_count + %s
                    WHERE product_id = %s
                    """,
                    (
                        item["quantity"],
                        item["product_id"]
                    )
                )

            cursor.execute(
                """
                UPDATE orders
                SET order_status = %s
                WHERE order_id = %s
                """,
                (
                    "CANCELLED",
                    order_id
                )
            )

            cursor.execute(
                """
                INSERT INTO order_status_history
                (
                    order_id,
                    order_status,
                    remarks
                )
                VALUES
                (%s,%s,%s)
                """,
                (
                    order_id,
                    "CANCELLED",
                    "Order cancelled"
                )
            )

            conn.commit()

            publish_event(
                "OrderCancelled",
                {
                    "orderId": order_id,
                    "status": "CANCELLED"
                }
            )

            return response(
                200,
                {
                    "message": "Order cancelled successfully",
                    "orderId": order_id,
                    "status": "CANCELLED"
                }
            )

    except Exception as e:

        conn.rollback()

        return response(
            500,
            {
                "message": str(e)
            }
        )

    finally:
        conn.close()

def handler(event, context):
    initialize_schema()
    method = event["httpMethod"]
    path = event["path"]
    role = event["requestContext"]["authorizer"]["role"]

    if method == "POST" and path.endswith("/customers"):

        if role not in ["CUSTOMER", "ADMIN"]:
            return response(
                403,
                {"message": "Access Denied"}
            )

        return create_customer(event)

    if method == "GET":

        if "/customers/" in path:

            if role != "ADMIN":
                return response(
                    403,
                    {"message": "Access Denied"}
                )

            customer_id = path.split("/")[-1]

            return get_customer_by_id(customer_id)

        if path.endswith("/customers"):

            if role != "ADMIN":
                return response(
                    403,
                    {"message": "Access Denied"}
                )

            return get_customers()

    if method == "POST" and path.endswith("/orders"):

        if role not in ["CUSTOMER", "ADMIN"]:
            return response(
                403,
                {"message": "Access Denied"}
            )

        return create_order(event)


    if method == "GET":

        query = event.get("queryStringParameters") or {}

        if "customerId" in query:

            if role not in ["CUSTOMER", "ADMIN"]:
                return response(
                    403,
                    {"message": "Access Denied"}
                )

            return get_customer_orders(
                query["customerId"]
            )
        if path.endswith("/orders"):

            if role != "ADMIN":
                return response(
                    403,
                    {"message": "Access Denied"}
                )

            return get_all_orders()
        

        parts = path.split("/")

        if len(parts) > 2:

            return get_order(parts[-1])
    
    if method == "PUT" and "/orders/" in path:

        if role not in ["CUSTOMER", "ADMIN"]:
            return response(
                403,
                {
                    "message": "Access Denied"
                }
            )

        order_id = path.split("/")[-1]

        return cancel_order(order_id)

    return response(
        404,
        {
            "message": "Route not found"
        }
    )



