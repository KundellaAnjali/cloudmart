import json
import uuid
import pymysql
import boto3
import os
import secrets
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def log(level, operation, message, **kwargs):
    log_data = {
        "level": level,
        "operation": operation,
        "message": message
    }

    log_data.update(kwargs)

    if level == "ERROR":
        logger.error(json.dumps(log_data))
    elif level == "WARNING":
        logger.warning(json.dumps(log_data))
    else:
        logger.info(json.dumps(log_data))

ssm = boto3.client("ssm")
events = boto3.client("events")
cloudwatch = boto3.client("cloudwatch")

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")

DB_HOST = ssm.get_parameter(
    Name=f"/cloudmart/{ENVIRONMENT}/db/host"
)["Parameter"]["Value"]

DB_NAME = ssm.get_parameter(
    Name=f"/cloudmart/{ENVIRONMENT}/db/name"
)["Parameter"]["Value"]

DB_USER = ssm.get_parameter(
    Name=f"/cloudmart/{ENVIRONMENT}/db/username"
)["Parameter"]["Value"]

DB_PASSWORD = ssm.get_parameter(
    Name=f"/cloudmart/{ENVIRONMENT}/db/password",
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

def create_customer(event):
    token = secrets.token_hex(32)

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

    log(
        "INFO",
        "CreateCustomer",
        "Customer creation request received",
        customer_name=customer_name,
        customer_email=customer_email
    )

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO customers
                (
                    customer_name,
                    customer_email,
                    auth_token,
                    role
                )
                VALUES
                (%s,%s,%s,%s)
                """,
                (
                    customer_name,
                    customer_email,
                    token,
                    "CUSTOMER"
                )
            )

            customer_id = cursor.lastrowid

            conn.commit()

            log(
                "INFO",
                "CreateCustomer",
                "Customer created successfully",
                customer_id=customer_id
            )

            return response(
                201,
                {
                    "message": "Customer created successfully",
                    "customerId": customer_id,
                    "authToken": token
                }
            )
            

    except Exception as e:

        conn.rollback()

        log(
            "ERROR",
            "CreateCustomer",
            "Customer creation failed",
            error=repr(e)
        )

        return response(
            500,
            {
                "message": repr(e)
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
                log(
                    "WARNING",
                    "GetCustomerById",
                    "Customer not found",
                    customer_id=customer_id
                )
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
    #customer_id = event["requestContext"]["authorizer"]["customer_id"]
    items = body.get("items", [])

    log(
        "INFO",
        "CreateOrder",
        "Order creation started",
        customer_id=customer_id
    )

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

                log(
                    "INFO",
                    "CreateOrder",
                    "Product validated",
                    product_id=product_id,
                    quantity=quantity
                )

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
                    publish_metric("FailedOrders")
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
                    publish_metric("FailedOrders")
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

                log(
                    "INFO",
                    "CreateOrder",
                    "Creating order record",
                    total_amount=total_amount
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
                publish_metric(
                    "InventoryDeductions",
                    quantity
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
                    publish_metric("LowStockProducts")
                    publish_event(
                        "LowStock",
                        {
                            "subject": "CloudMart Low Stock Alert",
                            "message": f"""
                    Dear Product Owner,

                    A product has fallen below the configured inventory threshold.

                    Product Details
                    ----------------------------------------
                    Product ID      : {product['product_id']}
                    Product Name    : {product['product_name']}
                    Current Stock   : {updated_product['stock_count']}
                    Threshold Value : {threshold}

                    Please replenish inventory at the earliest.

                    Regards,
                    CloudMart Inventory Monitoring
                    """
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
            publish_metric("OrdersCreated")
            publish_metric(
                "OrderValue",
                total_amount
            )
            
            publish_event(
                "OrderConfirmed",
                {
                    "subject": "CloudMart Order Confirmation",
                    "message": f"""
            Dear {customer['customer_name']},

            Your order has been successfully confirmed.

            Order Details
            ----------------------------------------
            Order ID      : {order_id}
            Customer ID   : {customer_id}
            Status        : CONFIRMED
            Total Amount  : ₹{total_amount}

            Products Ordered:
            {chr(10).join([
                f"• {item['product']['product_name']}\n"
                f"  Quantity   : {item['quantity']}\n"
                f"  Unit Price : ₹{item['product']['price']}"
                for item in product_details
            ])}

            Thank you for shopping with CloudMart.

            Regards,
            CloudMart Team
            """
                }
            )

            log(
                "INFO",
                "CreateOrder",
                "Order created successfully",
                order_id=order_id,
                total_amount=total_amount
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

        log(
            "INFO",
            "CancelOrder",
            "Order cancelled successfully",
            order_id=order_id
        )

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

                log(
                    "WARNING",
                    "GetOrder",
                    "Order not found",
                    order_id=order_id
                )

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
    log(
        "INFO",
        "CancelOrder",
        "Order cancellation requested",
        order_id=order_id
    )

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

                log(
                    "INFO",
                    "CancelOrder",
                    "Order cancelled successfully",
                    order_id=order_id
                )
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
                    "subject": "CloudMart Order Cancellation",
                    "message": f"""
            Dear Customer,

            Your order has been cancelled successfully.

            Order ID : {order_id}
            Status   : CANCELLED

            If this was not expected, please contact support.

            Regards,
            CloudMart Team
            """
                }
            )

            log(
                "ERROR",
                "CancelOrder",
                "Order cancellation failed",
                order_id=order_id
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
    log(
        "INFO",
        "Handler",
        "Lambda handler started"
    )

    initialize_schema()
    method = event["httpMethod"]
    path = event["path"]
    role = event["requestContext"]["authorizer"]["role"]  

    if method == "POST" and path.endswith("/customers"):
        return create_customer(event)

    if method == "GET":

        if "/customers/" in path:
            customer_id = path.split("/")[-1]
            return get_customer_by_id(customer_id)

        if path.endswith("/customers"):
            return get_customers()

    if method == "POST" and path.endswith("/orders"):
        return create_order(event)


    if method == "GET":

        query = event.get("queryStringParameters") or {}

        if "customerId" in query:
            return get_customer_orders(
                query["customerId"]
            )
        if path.endswith("/orders"):
            return get_all_orders()
        

        parts = path.split("/")

        if len(parts) > 2:

            return get_order(parts[-1])
    
    if method == "PATCH" and "/orders/" in path:
        order_id = path.split("/")[-1]

        return cancel_order(order_id)

    return response(
        404,
        {
            "message": "Route not found"
        }
    )



