from flask import Flask, render_template, redirect, Response
from flask import (
    Flask,
    render_template,
    redirect,
    Response,
    request,
    session,
    url_for
)
import boto3
import pymysql
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "cloudmart-dashboard-secret"

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
ec2 = boto3.client(
    "ec2",
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

def get_dashboard_instance_id():

    response = ec2.describe_instances(
        Filters=[
            {
                "Name": "tag:Name",
                "Values": ["Ec2DashboardV"]
            },
            {
                "Name": "instance-state-name",
                "Values": ["running"]
            }
        ]
    )

    reservations = response.get("Reservations", [])

    if not reservations:
        return None

    return reservations[0]["Instances"][0]["InstanceId"]
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

def get_lambda_metric(function_name, metric_name, stat="Sum"):
    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/Lambda",
        MetricName=metric_name,
        Dimensions=[
            {
                "Name": "FunctionName",
                "Value": function_name
            }
        ],
        StartTime=datetime.utcnow() - timedelta(hours=1),
        EndTime=datetime.utcnow(),
        Period=300,
        Statistics=[stat]
    )

    datapoints = response["Datapoints"]

    if not datapoints:
        return 0

    latest = sorted(
        datapoints,
        key=lambda x: x["Timestamp"]
    )[-1]

    return round(latest[stat], 2)

def get_rds_metric(metric_name):
    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/RDS",
        MetricName=metric_name,
        Dimensions=[
            {
                "Name": "DBInstanceIdentifier",
                "Value": "cloudmart-db"
            }
        ],
        StartTime=datetime.utcnow() - timedelta(hours=1),
        EndTime=datetime.utcnow(),
        Period=300,
        Statistics=["Average"]
    )

    datapoints = response["Datapoints"]

    if not datapoints:
        return 0

    return round(
        sorted(
            datapoints,
            key=lambda x: x["Timestamp"]
        )[-1]["Average"],
        2
    )
def get_ec2_metric(metric_name, instance_id):
    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName=metric_name,
        Dimensions=[
            {
                "Name": "InstanceId",
                "Value": instance_id
            }
        ],
        StartTime=datetime.utcnow() - timedelta(hours=1),
        EndTime=datetime.utcnow(),
        Period=300,
        Statistics=["Average"]
    )

    datapoints = response["Datapoints"]

    if not datapoints:
        return 0

    return round(
        sorted(
            datapoints,
            key=lambda x: x["Timestamp"]
        )[-1]["Average"],
        2
    )
def get_api_metric(metric_name):

    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/ApiGateway",
        MetricName=metric_name,
        StartTime=datetime.utcnow() - timedelta(hours=1),
        EndTime=datetime.utcnow(),
        Period=300,
        Statistics=["Sum"]
    )

    datapoints = response["Datapoints"]

    if not datapoints:
        return 0

    return int(
        sorted(
            datapoints,
            key=lambda x: x["Timestamp"]
        )[-1]["Sum"]
    )


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

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        token = request.form.get("token")

        conn = get_connection()

        try:

            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        customer_id,
                        customer_name,
                        role
                    FROM customers
                    WHERE customer_name = %s
                    AND auth_token = %s
                    AND is_active = TRUE
                    AND role = 'ADMIN'
                """, (username, token))

                admin = cursor.fetchone()

            if admin:

                session["logged_in"] = True
                session["admin_name"] = admin["customer_name"]

                return redirect(url_for("dashboard"))

        finally:
            conn.close()

        return render_template(
            "login.html",
            error="Invalid admin credentials"
        )

    return render_template("login.html")
@app.route("/")
def dashboard():

    if not session.get("logged_in"):
        return redirect(url_for("login"))

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
        authorizer_errors = get_lambda_metric(
            "cloudmart-authorizer",
            "Errors"
        )

        product_errors = get_lambda_metric(
            "cloudmart-product-function",
            "Errors"
        )

        order_errors = get_lambda_metric(
            "cloudmart-order-function",
            "Errors"
        )

        report_errors = get_lambda_metric(
            "cloudmart-report-function-dev",
            "Errors"
        )

        authorizer_invocations = get_lambda_metric(
            "cloudmart-authorizer",
            "Invocations"
        )

        product_invocations = get_lambda_metric(
            "cloudmart-product-function",
            "Invocations"
        )

        order_invocations = get_lambda_metric(
            "cloudmart-order-function",
            "Invocations"
        )

        report_invocations = get_lambda_metric(
            "cloudmart-report-function-dev",
            "Invocations"
        )
        rds_cpu = get_rds_metric(
            "CPUUtilization"
        )

        rds_connections = get_rds_metric(
            "DatabaseConnections"
        )
        
        instance_id = get_dashboard_instance_id()

        ec2_cpu = 0

        if instance_id:
            ec2_cpu = get_ec2_metric(
                "CPUUtilization",
                instance_id
            )

        # Alarms
        s3_alarm = get_alarm_state(
            "CloudMart-S3AccessFailures"
        )

        parameter_alarm = get_alarm_state(
            "CloudMart-ParameterAccessFailures"
        )

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
        authorizer_errors_alarm = get_alarm_state(
            "CloudMart-AuthorizerErrors"
        )

        product_errors_alarm = get_alarm_state(
            "CloudMart-ProductErrors"
        )

        order_errors_alarm = get_alarm_state(
            "CloudMart-OrderErrors"
        )

        report_errors_alarm = get_alarm_state(
            "CloudMart-ReportErrors"
        )

        ec2_cpu_alarm = get_alarm_state(
            "CloudMart-EC2HighCPU"
        )

        rds_cpu_alarm = get_alarm_state(
            "CloudMart-RDSHighCPU"
        )

        rds_connections_alarm = get_alarm_state(
            "CloudMart-RDSConnections"
        )

        api_4xx_alarm = get_alarm_state(
            "CloudMart-ApiGateway4XX"
        )

        api_5xx_alarm = get_alarm_state(
            "CloudMart-ApiGateway5XX"
        )
        authorizer_throttles = get_lambda_metric(
            "cloudmart-authorizer",
            "Throttles"
        )

        product_throttles = get_lambda_metric(
            "cloudmart-product-function",
            "Throttles"
        )

        order_throttles = get_lambda_metric(
            "cloudmart-order-function",
            "Throttles"
        )

        report_throttles = get_lambda_metric(
            "cloudmart-report-function-dev",
            "Throttles"
        )

        api_4xx = get_api_metric("4XXError")
        api_5xx = get_api_metric("5XXError")  
        

        # Health

        health_status = {}

        try:
            test_conn = get_connection()
            test_conn.close()
            health_status["RDS"] = "Healthy"
        except:
            health_status["RDS"] = "Unhealthy"

        health_status["S3"] = (
            "Critical"
            if s3_alarm
            else "Healthy"
        )


        health_status["Parameter Store"] = (
            "Critical"
            if parameter_alarm
            else "Healthy"
        )

        rds_connection_failure_alarm = get_alarm_state(
            "CloudMart-RDSConnectionFailures"
        )

        health_status["RDS"] = (
            "Critical"
            if (
                rds_cpu_alarm
                or rds_connections_alarm
                or rds_connection_failure_alarm
            )
            else "Healthy"
        )

        health_status["EC2"] = (
            "Critical"
            if ec2_cpu_alarm
            else "Healthy"
        )

        health_status["API Gateway"] = (
            "Critical"
            if api_5xx_alarm
            else "Warning"
            if api_4xx_alarm
            else "Healthy"
        )

        health_status["Authorizer Lambda"] = (
            "Critical"
            if authorizer_errors_alarm
            else "Healthy"
        )

        health_status["Product Lambda"] = (
            "Critical"
            if product_errors_alarm
            else "Healthy"
        )

        health_status["Order Lambda"] = (
            "Critical"
            if order_errors_alarm
            else "Healthy"
        )

        health_status["Report Lambda"] = (
            "Critical"
            if report_errors_alarm
            else "Healthy"
        )
        schema_init_alarm = get_alarm_state(
            "CloudMart-SchemaInitErrors"
        )

        health_status["Schema Init Lambda"] = (
            "Critical"
            if schema_init_alarm
            else "Healthy"
        )
        health_status["Authorizer Lambda"] = (
            "Critical"
            if authorizer_errors_alarm
            else "Warning"
            if authorizer_throttles > 0
            else "Healthy"
        )
        health_status["Product Lambda"] = (
            "Critical"
            if product_errors_alarm
            else "Warning"
            if product_throttles > 0
            else "Healthy"
        )
        health_status["Order Lambda"] = (
            "Critical"
            if order_errors_alarm
            else "Warning"
            if order_throttles > 0
            else "Healthy"
        )
        health_status["Report Lambda"] = (
            "Critical"
            if report_errors_alarm
            else "Warning"
            if report_throttles > 0
            else "Healthy"
        )


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
            unauthorized_requests=unauthorized_requests,

            reports_generated=reports_generated,
            report_upload_success=report_upload_success,
            report_generation_failures=report_generation_failures,

            authorizer_errors=authorizer_errors,
            product_errors=product_errors,
            order_errors=order_errors,
            report_errors=report_errors,

            authorizer_invocations=authorizer_invocations,
            product_invocations=product_invocations,
            order_invocations=order_invocations,
            report_invocations=report_invocations,

            authorizer_throttles=authorizer_throttles,
            product_throttles=product_throttles,
            order_throttles=order_throttles,
            report_throttles=report_throttles,

            api_4xx=api_4xx,
            api_5xx=api_5xx,

            ec2_cpu=ec2_cpu,

            rds_cpu=rds_cpu,
            rds_connections=rds_connections,

            failed_orders_alarm=failed_orders_alarm,
            low_stock_alarm=low_stock_alarm,
            unauthorized_alarm=unauthorized_alarm,
            report_alarm=report_alarm,

            authorizer_errors_alarm=authorizer_errors_alarm,
            product_errors_alarm=product_errors_alarm,
            order_errors_alarm=order_errors_alarm,
            report_errors_alarm=report_errors_alarm,

            ec2_cpu_alarm=ec2_cpu_alarm,
            rds_cpu_alarm=rds_cpu_alarm,
            rds_connections_alarm=rds_connections_alarm,

            api_4xx_alarm=api_4xx_alarm,
            api_5xx_alarm=api_5xx_alarm,

            s3_alarm=s3_alarm,
            parameter_alarm=parameter_alarm,

            schema_init_alarm=schema_init_alarm,
            rds_connection_failure_alarm=rds_connection_failure_alarm,
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
    try:
        obj = s3.get_object(
            Bucket=REPORTS_BUCKET,
            Key=key
        )

        # Pass raw bytes directly to Flask's Response to avoid manual decoding overhead
        return Response(
            obj["Body"].read(),
            mimetype="text/plain"
        )
    except Exception as e:
        return f"Error loading report: {str(e)}", 404

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
@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False) 