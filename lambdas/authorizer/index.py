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
            "*"
        )

    elif role == "PRODUCT":

        if "/customers" in method_arn or "/orders" in method_arn:
            return generate_policy(
                role,
                "Deny",
                method_arn
            )

        return generate_policy(
            role,
            "Allow",
            "*"
        )

    elif role == "CUSTOMER":

        if any(x in method_arn for x in [
            "/POST/products",
            "/PATCH/products",
            "/DELETE/products"
        ]):
            return generate_policy(
                role,
                "Deny",
                method_arn
            )

        return generate_policy(
            role,
            "Allow",
            "*"
        )