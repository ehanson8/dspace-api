import boto3


class S3Client:
    @classmethod
    def get_client(cls):
        return boto3.client("s3")
