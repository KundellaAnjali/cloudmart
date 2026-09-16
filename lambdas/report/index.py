import json
import logging
import csv
import io
import boto3
import pymysql
import os
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)
ssm = boto3.client("ssm")
s3 = boto3.client("s3")
cloudwatch = boto3.client("cloudwatch")

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")

def get_parameter(name, decrypt=False):

    response = ssm.get_parameter(
        Name=name,
        WithDecryption=decrypt
    )

    return response["Parameter"]["Value"]

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

def get_connection():

    return pymysql.connect(
        host=get_parameter(
            f"/cloudmart/{ENVIRONMENT}/db/host"
        ),
        user=get_parameter(
            f"/cloudmart/{ENVIRONMENT}/db/username"
        ),
        password=get_parameter(
            f"/cloudmart/{ENVIRONMENT}/db/password",
            decrypt=True
        ),
        database=get_parameter(
            f"/cloudmart/{ENVIRONMENT}/db/name"
        ),
        cursorclass=pymysql.cursors.DictCursor
    )



    
def handler(event, context):
    logger.info("Report generation started")
    conn = None

    try:

        conn = get_connection()

        with conn.cursor() as cursor:

            cursor.execute("""
                SELECT
                    product_id,
                    product_name,
                    category,
                    price,
                    stock_count
                FROM product
                WHERE is_active = TRUE
            """)

            products = cursor.fetchall()

            cursor.execute("""
                SELECT
                    order_id,
                    customer_id,
                    order_status,
                    total_amount
                FROM orders
            """)

            orders = cursor.fetchall()

        # -----------------------------
        # BUSINESS METRICS
        # -----------------------------

        total_products = len(products)

        total_orders = len(orders)

        confirmed_orders = len(
            [
                order
                for order in orders
                if order["order_status"] == "CONFIRMED"
            ]
        )

        cancelled_orders = len(
            [
                order
                for order in orders
                if order["order_status"] == "CANCELLED"
            ]
        )

        total_revenue = sum(
            float(order["total_amount"])
            for order in orders
            if order["order_status"] == "CONFIRMED"
        )

        low_stock_products = len(
            [
                product
                for product in products
                if product["stock_count"] < 10
            ]
        )

        average_order_value = (
            total_revenue / confirmed_orders
            if confirmed_orders > 0
            else 0
        )

        highest_order = max(
            orders,
            key=lambda order: float(order["total_amount"]),
            default=None
        )

        # -----------------------------
        # CSV GENERATION
        # -----------------------------

        output = io.StringIO()

        writer = csv.writer(output)

        writer.writerow([
            "CLOUDMART BUSINESS REPORT"
        ])

        writer.writerow([
            "Generated On",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])

        writer.writerow([])

        # -----------------------------
        # BUSINESS SUMMARY
        # -----------------------------

        writer.writerow(["BUSINESS SUMMARY"])

        writer.writerow([
            "Total Products",
            total_products
        ])

        writer.writerow([
            "Total Orders",
            total_orders
        ])

        writer.writerow([
            "Confirmed Orders",
            confirmed_orders
        ])

        writer.writerow([
            "Cancelled Orders",
            cancelled_orders
        ])

        writer.writerow([
            "Total Revenue",
            total_revenue
        ])

        writer.writerow([
            "Average Order Value",
            round(average_order_value, 2)
        ])

        writer.writerow([
            "Low Stock Products",
            low_stock_products
        ])

        if highest_order:

            writer.writerow([
                "Highest Value Order",
                highest_order["order_id"]
            ])

            writer.writerow([
                "Highest Order Amount",
                float(
                    highest_order["total_amount"]
                )
            ])

        writer.writerow([])

        # -----------------------------
        # PRODUCT DETAILS
        # -----------------------------

        writer.writerow(["PRODUCT DETAILS"])

        writer.writerow([
            "Product ID",
            "Product Name",
            "Category",
            "Price",
            "Stock Count"
        ])

        for product in products:

            writer.writerow([
                product["product_id"],
                product["product_name"],
                product["category"],
                float(product["price"]),
                product["stock_count"]
            ])

        writer.writerow([])

        # -----------------------------
        # ORDER DETAILS
        # -----------------------------

        writer.writerow(["ORDER DETAILS"])

        writer.writerow([
            "Order ID",
            "Customer ID",
            "Status",
            "Amount"
        ])

        for order in orders:

            writer.writerow([
                order["order_id"],
                order["customer_id"],
                order["order_status"],
                float(order["total_amount"])
            ])

        # -----------------------------
        # METRIC
        # -----------------------------

        publish_metric(
            "ReportsGenerated"
        )

        bucket_name = get_parameter(
            f"/cloudmart/{ENVIRONMENT}/s3/reports-bucket"
        )

        file_name = (
            f"reports/cloudmart-business-report-"
            f"{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.csv"
        )

        s3.put_object(
            Bucket=bucket_name,
            Key=file_name,
            Body=output.getvalue(),
            ContentType="text/csv"
        )

        publish_metric(
            "ReportUploadSuccess"
        )

        output.close()

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Business report generated successfully",
                    "file": file_name,
                    "bucket": bucket_name
                }
            )
        }

    except Exception as e:

        try:

            publish_metric(
                "ReportGenerationFailures"
            )

        except Exception:
            pass

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "error": str(e)
                }
            )
        }

    finally:

        if conn:
            conn.close()
