import boto3
ssm = boto3.client('ssm')

def handler(event, context):

    token = event.get("authorizationToken", "")

    response = ssm.get_parameter(
        Name="/cloudmart/dev/auth/token",
        WithDecryption=True
    )

    valid_token = response["Parameter"]["Value"]

    if token == f"Bearer {valid_token}":
        return {
            "principalId": "cloudmart",
            "policyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "execute-api:Invoke",
                        "Effect": "Allow",
                        "Resource": "*"
                    }
                ]
            }
        }

    raise Exception("Unauthorized")