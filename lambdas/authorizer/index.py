import boto3
import os
import pymysql
import json

ssm = boto3.client("ssm")

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")

def get_connection():

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

    return pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor
    )

def get_parameter(name, decrypt=False):
    response = ssm.get_parameter(
        Name=name,
        WithDecryption=decrypt
    )
    return response["Parameter"]["Value"]

def generate_policy(
    principal_id,
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
        },
        "context": {
            "role": role,
            "customer_id": str(customer_id),
            "customer_name": customer_name
        }
    }
def handler(event, context):

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

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

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

            user = cursor.fetchone()

    finally:
        conn.close()

    if not user:
        raise Exception("Unauthorized")

    if not user["is_active"]:
        raise Exception("Unauthorized")

    role = user["role"]


    if role == "ADMIN":

        return generate_policy(
            str(user["customer_id"]),
            role,
            user["customer_id"],
            user["customer_name"],
            "Allow",
            "*"
        )

    elif role == "PRODUCT":

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
  