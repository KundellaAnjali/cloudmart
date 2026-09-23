import boto3
import os
import pymysql
import json
import logging
ssm = boto3.client("ssm")
cloudwatch = boto3.client("cloudwatch") # used for custom metrics

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
logger = logging.getLogger() #gets the root logger.
logger.setLevel(logging.INFO)
def get_connection():
    logger.info("Creating database connection")

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
    #Lambda connects to RDS.
    return pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor
    )

def get_parameter(name, decrypt=False):
    logger.info(f"Fetching parameter: {name}")
    response = ssm.get_parameter(
        Name=name,
        WithDecryption=decrypt
    )
    return response["Parameter"]["Value"]
# creates authorization response to understand to the api gateway
def generate_policy(
    principal_id, # indentify the authonticated user
    role,
    customer_id,
    customer_name,
    effect,
    resources
):
    return {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": resources
                }
            ]
        }, # it is sending additional data from authorizer to api gateway
        "context": {
            "role": role,
            "customer_id": str(customer_id),
            "customer_name": customer_name
        }
    }

def publish_metric(metric_name):

    logger.info(
        f"Publishing metric: {metric_name}"
    )

    cloudwatch.put_metric_data(
        Namespace="CloudMart",
        MetricData=[
            {
                "MetricName": metric_name,
                "Value": 1,
                "Unit": "Count"
            }
        ]
    )

def handler(event, context):
    logger.info(
        f"Authorization request received. "
        f"Method ARN: {event['methodArn']}"
    )

    token = event.get("authorizationToken", "")
    method_arn = event["methodArn"]
    print("METHOD ARN:", method_arn)

    arn_parts = method_arn.split(":")
    api_gateway_part = arn_parts[5]

    api_id = api_gateway_part.split("/")[0]
    stage = api_gateway_part.split("/")[1]

    base_arn = (
        f"arn:aws:execute-api:"
        f"{arn_parts[3]}:"
        f"{arn_parts[4]}:"
        f"{api_id}/{stage}"
    )

    token = token.replace("Bearer ", "")
    logger.info(
        f"Token received: {token[:10]}..."
    )

    conn = get_connection()

    try:

        with conn.cursor() as cursor:
            logger.info(
                "Validating token against customer table"
            )
            cursor.execute(
                """
                SELECT
                    customer_id,
                    customer_name,
                    role,
                    is_active
                FROM customers
                WHERE auth_token = %s
                AND is_active = TRUE
                """,
                (token,)
            )

            user = cursor.fetchone()  # get details of customer if match occurs

    finally:
        conn.close()

    if not user:
        publish_metric("UnauthorizedRequests")
        logger.error(json.dumps({
            "level": "ERROR",
            "operation": "Authorizer",
            "message": "Invalid token",
            "token": token
        }))
        raise Exception("Unauthorized")

    role = user["role"]
    publish_metric("AuthorizedRequests")
    logger.info(json.dumps({
        "level": "INFO",
        "operation": "Authorizer",
        "message": "Token validated successfully",
        "customer_id": user["customer_id"],
        "customer_name": user["customer_name"],
        "role": role
    }))

    if role == "ADMIN":
        logger.info(
            f"Generating ADMIN policy "
            f"for {user['customer_name']}"
        )

        return generate_policy(
            str(user["customer_id"]),
            role,
            user["customer_id"],
            user["customer_name"],
            "Allow",
            "*"
        )

    elif role == "PRODUCT":
        logger.info(
            f"Generating PRODUCT policy "
            f"for {user['customer_name']}"
        )
        return generate_policy(
            str(user["customer_id"]),
            role,
            user["customer_id"],
            user["customer_name"],
            "Allow",
            [
                f"{base_arn}/GET/products",
                f"{base_arn}/GET/products/*",

                f"{base_arn}/POST/products",
                f"{base_arn}/PATCH/products/*",
                f"{base_arn}/DELETE/products/*"
            ]
        )


    elif role == "CUSTOMER":
        logger.info(
            f"Generating CUSTOMER policy "
            f"for {user['customer_name']}"
        )
        return generate_policy(
            str(user["customer_id"]),
            role,
            user["customer_id"],
            user["customer_name"],
            "Allow",
            [
                f"{base_arn}/GET/products",
                f"{base_arn}/GET/products/*",

                f"{base_arn}/POST/customers",
                f"{base_arn}/GET/customers/*",

                f"{base_arn}/POST/orders",
                f"{base_arn}/GET/orders",
                f"{base_arn}/GET/orders/*",
                f"{base_arn}/PATCH/orders/*"
            ]
        )
  