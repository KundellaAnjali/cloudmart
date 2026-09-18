from flask import Flask, render_template
import boto3
import pymysql
from datetime import datetime, timedelta

app = Flask(__name__)

ENVIRONMENT = "dev"

# AWS Clients

ssm = boto3.client(
    "ssm",
    region_name="ap-south-1"
)
s3 = boto3.client(
    "s3",
    region_name="ap-south-1"
)
cloudwatch = boto3.client(
    "cloudwatch",
    region_name="ap-south-1"
)
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
def dashboard():

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute("""
                SELECT COUNT(*) total_products
                FROM product
                WHERE is_active = TRUE
            """)
            total_products = cursor.fetchone()["total_products"]

            cursor.execute("""
                SELECT COUNT(*) total_orders
                FROM orders
            """)
            total_orders = cursor.fetchone()["total_orders"]

            cursor.execute("""
                SELECT COUNT(*) total_customers
                FROM customers
                WHERE is_active = TRUE
            """)
            total_customers = cursor.fetchone()["total_customers"]

            cursor.execute("""
                SELECT COALESCE(
                    SUM(total_amount),
                    0
                ) revenue
                FROM orders
                WHERE order_status='CONFIRMED'
            """)
            revenue = cursor.fetchone()["revenue"]

            cursor.execute("""
                SELECT COUNT(*) low_stock
                FROM product
                WHERE stock_count < 10
            """)
            low_stock = cursor.fetchone()["low_stock"]

            cursor.execute("""
                SELECT COUNT(*) failed_orders
                FROM orders
                WHERE order_status='CANCELLED'
            """)
            failed_orders = cursor.fetchone()["failed_orders"]

        return render_template(
            "dashboard.html",
            total_products=total_products,
            total_orders=total_orders,
            total_customers=total_customers,
            revenue=revenue,
            low_stock=low_stock,
            failed_orders=failed_orders
        )

    finally:

        conn.close()

@app.route("/products")
def products():

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute("""
                SELECT
                    product_id,
                    product_name,
                    category,
                    price,
                    stock_count,
                    is_active
                FROM product
                ORDER BY product_name
            """)

            products = cursor.fetchall()

        return render_template(
            "products.html",
            products=products
        )

    finally:

        conn.close()


@app.route("/orders")
def orders():

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute("""
                SELECT COUNT(*) total_orders
                FROM orders
            """)
            total_orders = cursor.fetchone()["total_orders"]

            cursor.execute("""
                SELECT COUNT(*) confirmed_orders
                FROM orders
                WHERE order_status='CONFIRMED'
            """)
            confirmed_orders = cursor.fetchone()["confirmed_orders"]

            cursor.execute("""
                SELECT COUNT(*) cancelled_orders
                FROM orders
                WHERE order_status='CANCELLED'
            """)
            cancelled_orders = cursor.fetchone()["cancelled_orders"]

            cursor.execute("""
                SELECT
                    COALESCE(
                        SUM(total_amount),
                        0
                    ) revenue
                FROM orders
                WHERE order_status='CONFIRMED'
            """)
            revenue = cursor.fetchone()["revenue"]

            cursor.execute("""
                SELECT
                    order_id,
                    customer_id,
                    order_status,
                    total_amount,
                    order_date
                FROM orders
                ORDER BY order_date DESC
            """)
            orders = cursor.fetchall()

        return render_template(
            "orders.html",
            total_orders=total_orders,
            confirmed_orders=confirmed_orders,
            cancelled_orders=cancelled_orders,
            revenue=revenue,
            orders=orders
        )

    finally:

        conn.close()


@app.route("/customers")
def customers():

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute("""
                SELECT
                    customer_id,
                    customer_name,
                    customer_email,
                    role,
                    is_active,
                    created_at
                FROM customers
                ORDER BY customer_name
            """)

            customers = cursor.fetchall()

            cursor.execute("""
                SELECT COUNT(*) total_customers
                FROM customers
                WHERE is_active = TRUE
            """)

            total_customers = cursor.fetchone()["total_customers"]

        return render_template(
            "customers.html",
            customers=customers,
            total_customers=total_customers
        )

    finally:

        conn.close()


@app.route("/reports")
def reports():

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
        ):

            reports.append({

                "name":
                report["Key"].split("/")[-1],

                "key":
                report["Key"],

                "date":
                report["LastModified"]

            })

    return render_template(
        "reports.html",
        reports=reports
    )


@app.route("/metrics")
def metrics():

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

    return render_template(
        "metrics.html",
        products_created=products_created,
        orders_created=orders_created,
        failed_orders=failed_orders,
        authorized_requests=authorized_requests,
        reports_generated=reports_generated,
        report_upload_success=report_upload_success,
        report_generation_failures=report_generation_failures
    )


@app.route("/alerts")
def alerts():

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
        "alerts.html",
        failed_orders_alarm=failed_orders_alarm,
        low_stock_alarm=low_stock_alarm,
        unauthorized_alarm=unauthorized_alarm,
        report_alarm=report_alarm
    )


@app.route("/health")
def health():

    health_status = {}

    try:
        conn = get_connection()
        conn.close()

        health_status["RDS"] = "Healthy"

    except:
        health_status["RDS"] = "Unhealthy"

    try:

        s3.list_objects_v2(
            Bucket=REPORTS_BUCKET,
            MaxKeys=1
        )

        health_status["S3"] = "Healthy"

    except:

        health_status["S3"] = "Unhealthy"

    try:

        cloudwatch.list_metrics(
            Namespace="CloudMart"
        )

        health_status["CloudWatch"] = "Healthy"

    except:

        health_status["CloudWatch"] = "Unhealthy"

    try:

        ssm.get_parameter(
            Name=f"/cloudmart/{ENVIRONMENT}/db/host"
        )

        health_status["Parameter Store"] = "Healthy"

    except:

        health_status["Parameter Store"] = "Unhealthy"

    return render_template(
        "health.html",
        health_status=health_status
    )

def old_dashboard():

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