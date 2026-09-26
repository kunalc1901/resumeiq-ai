import boto3

from core.config import settings


def fetch_pdf_bytes_from_s3(s3_key: str) -> bytes:
    """Fetch a PDF from S3 and return its contents in memory."""
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    response = s3.get_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
    return response["Body"].read()
