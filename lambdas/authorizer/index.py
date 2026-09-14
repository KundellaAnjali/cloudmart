import boto3
import os

ssm = boto3.client("ssm")

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")

def get_parameter(name):
    response = ssm.get_parameter(
        Name=name
    )
    return response["Parameter"]["Value"]

def generate_policy(role, effect, resource):
    return {
        "principalId": role,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": resource
                }
            ]
        },
        "context": {
            "role": role
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

    customer_token = get_parameter(
        f"/cloudmart/{ENVIRONMENT}/auth/customer-token"
    )

    product_token = get_parameter(
        f"/cloudmart/{ENVIRONMENT}/auth/product-token"
    )

    admin_token = get_parameter(
        f"/cloudmart/{ENVIRONMENT}/auth/admin-token"
    )

    if token == f"Bearer {customer_token}":
        role = "CUSTOMER"

    elif token == f"Bearer {product_token}":
        role = "PRODUCT"

    elif token == f"Bearer {admin_token}":
        role = "ADMIN"

    else:
        raise Exception("Unauthorized")

    if role == "ADMIN":

        return generate_policy(
            role,
            "Allow",
            [f"{base_arn}/*/*"]
        )

    elif role == "PRODUCT":

        return generate_policy(
            role,
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
            role,
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