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

            # Get Products

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

            # Get Orders

            cursor.execute("""
                SELECT
                    order_id,
                    customer_id,
                    order_status,
                    total_amount
                FROM orders
            """)

            orders = cursor.fetchall()

        # Create CSV

        output = io.StringIO()

        writer = csv.writer(output)

        writer.writerow([
            "CloudMart Daily Report"
        ])

        writer.writerow([
            "Generated On",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])

        writer.writerow([])

        # Products Section

        writer.writerow(["PRODUCTS"])

        writer.writerow([
            "Product ID",
            "Product Name",
            "Category",
            "Price",
            "Stock"
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

        # Orders Section

        writer.writerow(["ORDERS"])

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

        # Metric 1

        publish_metric("ReportsGenerated")

        bucket_name = get_parameter(
            f"/cloudmart/{ENVIRONMENT}/s3/reports-bucket"
        )

        file_name = (
            f"reports/report-"
            f"{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.csv"
        )

        s3.put_object(
            Bucket=bucket_name,
            Key=file_name,
            Body=output.getvalue(),
            ContentType="text/csv"
        )
        logger.info(
            f"Uploading report to {bucket_name}/{file_name}"
        )

        # Metric 2

        publish_metric("ReportUploadSuccess")
        output.close()
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Report generated successfully",
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

        print(f"ERROR: {str(e)}")

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