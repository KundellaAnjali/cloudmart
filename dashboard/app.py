from flask import Flask, render_template
import boto3
import pymysql
from datetime import datetime, timedelta

app = Flask(__name__)

ENVIRONMENT = "dev"

# AWS Clients

ssm = boto3.client("ssm")
s3 = boto3.client("s3")
cloudwatch = boto3.client("cloudwatch")

# Database Parameters

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

REPORTS_BUCKET = ssm.get_parameter(
    Name=f"/cloudmart/{ENVIRONMENT}/s3/reports-bucket"
)["Parameter"]["Value"]


def get_connection():

    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )


def get_metric_value(metric_name):

    response = cloudwatch.get_metric_statistics(
        Namespace="CloudMart",
        MetricName=metric_name,
        StartTime=datetime.utcnow() - timedelta(days=30),
        EndTime=datetime.utcnow(),
        Period=86400,
        Statistics=["Sum"]
    )

    datapoints = response["Datapoints"]

    if not datapoints:
        return 0

    latest = sorted(
        datapoints,
        key=lambda x: x["Timestamp"]
    )[-1]

    return int(latest["Sum"])

def get_alarm_state(alarm_name):

    response = cloudwatch.describe_alarms(
        AlarmNames=[alarm_name]
    )

    alarms = response["MetricAlarms"]

    if not alarms:
        return "UNKNOWN"

    return alarms[0]["StateValue"]


@app.route("/")
def home():

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            # Total Products

            cursor.execute("""
                SELECT COUNT(*) AS total_products
                FROM product
                WHERE is_active = TRUE
            """)

            total_products = cursor.fetchone()[
                "total_products"
            ]

            # Total Orders

            cursor.execute("""
                SELECT COUNT(*) AS total_orders
                FROM orders
            """)

            total_orders = cursor.fetchone()[
                "total_orders"
            ]

            # Revenue

            cursor.execute("""
                SELECT
                    COALESCE(
                        SUM(total_amount),
                        0
                    ) AS revenue
                FROM orders
                WHERE order_status='CONFIRMED'
            """)

            revenue = cursor.fetchone()[
                "revenue"
            ]

            # Low Stock Products

            cursor.execute("""
                SELECT COUNT(*) AS low_stock
                FROM product
                WHERE stock_count < 10
                AND is_active = TRUE
            """)

            low_stock = cursor.fetchone()[
                "low_stock"
            ]

            # Recent Orders

            cursor.execute("""
                SELECT
                    order_id,
                    customer_id,
                    order_status,
                    total_amount
                FROM orders
                ORDER BY order_date DESC
                LIMIT 5
            """)

            recent_orders = cursor.fetchall()

            # Inventory

            cursor.execute("""
                SELECT
                    product_id,
                    product_name,
                    category,
                    price,
                    stock_count
                FROM product
                WHERE is_active = TRUE
                ORDER BY product_name
            """)

            inventory = cursor.fetchall()

        # Reports From S3

        response = s3.list_objects_v2(
            Bucket=REPORTS_BUCKET,
            Prefix="reports/"
        )

        reports = []

        if "Contents" in response:

            for report in sorted(
                response["Contents"],
                key=lambda x: x["LastModified"],
                reverse=True
            )[:10]:

                reports.append(
                    {
                        "name": report["Key"].split("/")[-1],
                        "date": report["LastModified"]
                    }
                )

        # CloudWatch Metrics

        products_created = get_metric_value(
            "ProductsCreated"
        )

        orders_created = get_metric_value(
            "OrdersCreated"
        )

        failed_orders = get_metric_value(
            "FailedOrders"
        )

        authorized_requests = get_metric_value(
            "AuthorizedRequests"
        )

        reports_generated = get_metric_value(
            "ReportsGenerated"
        )

        report_upload_success = get_metric_value(
            "ReportUploadSuccess"
        )

        report_generation_failures = get_metric_value(
            "ReportGenerationFailures"
        )

        # CloudWatch Alarm States

        failed_orders_alarm = get_alarm_state(
            "CloudMart-FailedOrders"
        )

        low_stock_alarm = get_alarm_state(
            "CloudMart-LowStockProducts"
        )

        unauthorized_alarm = get_alarm_state(
            "CloudMart-UnauthorizedRequests"
        )

        report_alarm = get_alarm_state(
            "CloudMart-ReportGenerationFailures"
        )

        return render_template(
            "index.html",
            title="CloudMart Dashboard",
            total_products=total_products,
            total_orders=total_orders,
            revenue=revenue,
            low_stock=low_stock,
            recent_orders=recent_orders,
            inventory=inventory,
            reports=reports,
            products_created=products_created,
            orders_created=orders_created,
            failed_orders=failed_orders,
            authorized_requests=authorized_requests,
            reports_generated=reports_generated,
            report_upload_success=report_upload_success,
            report_generation_failures=report_generation_failures,
            failed_orders_alarm=failed_orders_alarm,
            low_stock_alarm=low_stock_alarm,
            unauthorized_alarm=unauthorized_alarm,
            report_alarm=report_alarm
        )

    finally:

        conn.close()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )