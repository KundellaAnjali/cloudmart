import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):

    logger.info("Report Lambda triggered")

    logger.info(json.dumps(event))

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Report Lambda working"
            }
        )
    }