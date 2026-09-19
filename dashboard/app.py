
from flask import Flask, render_template, redirect
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
        return 0

    state = alarms[0]["StateValue"]

    if state == "ALARM":
        return 1

    return 0



@app.route("/")
def dashboard():

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            # KPI Cards

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

            # Products

            cursor.execute("""
                SELECT
                    product_id,
                    product_name,
                    category,
                    price,
                    stock_count
                FROM product
                ORDER BY product_name
            """)
            products = cursor.fetchall()

            # Orders

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

            # Customers

            cursor.execute("""
                SELECT
                    customer_id,
                    customer_name,
                    customer_email,
                    role
                FROM customers
                ORDER BY customer_name
            """)
            customers = cursor.fetchall()

            # Best Selling Product

            cursor.execute("""
                SELECT
                    p.product_name,
                    SUM(oi.quantity) total_sold
                FROM order_items oi
                JOIN product p
                    ON oi.product_id = p.product_id
                GROUP BY p.product_name
                ORDER BY total_sold DESC
                LIMIT 1
            """)

            best_product = cursor.fetchone()

            # Lowest Selling Product

            cursor.execute("""
                SELECT
                    p.product_name,
                    SUM(oi.quantity) total_sold
                FROM order_items oi
                JOIN product p
                    ON oi.product_id = p.product_id
                GROUP BY p.product_name
                ORDER BY total_sold ASC
                LIMIT 1
            """)

            lowest_product = cursor.fetchone()

            # Highest Spending Customer

            cursor.execute("""
                SELECT
                    c.customer_id,
                    c.customer_name,
                    SUM(o.total_amount) total_spent
                FROM orders o
                JOIN customers c
                    ON o.customer_id = c.customer_id
                WHERE o.order_status = 'CONFIRMED'
                GROUP BY
                    c.customer_id,
                    c.customer_name
                ORDER BY total_spent DESC
                LIMIT 1
            """)



            top_spender = cursor.fetchone()

            # Customer With Most Orders

            cursor.execute("""
                SELECT
                    c.customer_id,
                    c.customer_name,
                    COUNT(*) total_orders
                FROM orders o
                JOIN customers c
                    ON o.customer_id = c.customer_id
                GROUP BY
                    c.customer_id,
                    c.customer_name
                ORDER BY total_orders DESC
                LIMIT 1
            """)

            top_customer = cursor.fetchone()

            

        # Reports

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
                    "name": report["Key"].split("/")[-1],
                    "date": report["LastModified"],
                    "key": report["Key"]
                })
        # Metrics

        products_created = get_metric_value(
            "ProductsCreated"
        )

        orders_created = get_metric_value(
            "OrdersCreated"
        )

        failed_orders_metric = get_metric_value(
            "FailedOrders"
        )

        authorized_requests = get_metric_value(
            "AuthorizedRequests"
        )

        unauthorized_requests = get_metric_value(
            "UnauthorizedRequests"
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

        # Alarms

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

        # Health

        health_status = {}

        try:
            test_conn = get_connection()
            test_conn.close()
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

            ssm.get_parameters(
                Names=[
                    f"/cloudmart/{ENVIRONMENT}/db/host",
                    f"/cloudmart/{ENVIRONMENT}/db/name",
                    f"/cloudmart/{ENVIRONMENT}/db/username",
                    f"/cloudmart/{ENVIRONMENT}/db/password",
                    f"/cloudmart/{ENVIRONMENT}/s3/reports-bucket"
                ],
                WithDecryption=True
            )

            health_status["Parameter Store"] = "Healthy"

        except:

            health_status["Parameter Store"] = "Unhealthy"

        

        return render_template(

            "dashboard.html",

            total_products=total_products,
            total_orders=total_orders,
            total_customers=total_customers,
            revenue=revenue,
            low_stock=low_stock,
            failed_orders=failed_orders,

            products=products,
            orders=orders,
            customers=customers,
            reports=reports,

            products_created=products_created,
            orders_created=orders_created,
            failed_orders_metric=failed_orders_metric,
            authorized_requests=authorized_requests,
            reports_generated=reports_generated,
            report_upload_success=report_upload_success,
            report_generation_failures=report_generation_failures,
            unauthorized_requests=unauthorized_requests,
            failed_orders_alarm=failed_orders_alarm,
            low_stock_alarm=low_stock_alarm,
            unauthorized_alarm=unauthorized_alarm,
            report_alarm=report_alarm,
            best_product=best_product,
            lowest_product=lowest_product,
            top_spender=top_spender,
            top_customer=top_customer,

            health_status=health_status
        )

finally:

    conn.close()


@app.route("/view-report/<path:key>")
def view_report(key):

    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": REPORTS_BUCKET,
            "Key": key
        },
        ExpiresIn=3600
    )

    return redirect(url)

@app.route("/download-report/<path:key>")
def download_report(key):

    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": REPORTS_BUCKET,
            "Key": key,
            "ResponseContentDisposition":
                f'attachment; filename="{key.split("/")[-1]}"'
        },
        ExpiresIn=3600
    )

    return redirect(url)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)