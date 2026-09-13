import boto3
import os

ssm = boto3.client("ssm")

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")


def get_parameter(name):
    response = ssm.get_parameter(
        Name=name
    )
    return response["Parameter"]["Value"]


def handler(event, context):

    token = event.get("authorizationToken", "")

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

    return {
        "principalId": role,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Allow",
                    "Resource": "*"
                }
            ]
        },
        "context": {
            "role": role
        }
    }