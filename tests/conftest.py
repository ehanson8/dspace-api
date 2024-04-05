import csv
import json
import yaml

import boto3
import pytest
import requests_mock
import smart_open

from click.testing import CliRunner
from moto import mock_aws

from dsaps import dspace


# Env fixtures
@pytest.fixture(autouse=True)
def _test_environment(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")


@pytest.fixture
def source_config():
    with smart_open.open("tests/fixtures/source_config.json", "r") as file:
        return yaml.safe_load(file)


@pytest.fixture
def source_metadata_csv():
    with open("tests/fixtures/source_metadata.csv") as file:
        reader = csv.DictReader(file)
        yield reader


@pytest.fixture
def source_metadata_csv_with_bitstreams():
    with open("tests/fixtures/updated-source_metadata.csv") as file:
        reader = csv.DictReader(file)
        yield reader


@pytest.fixture()
def dspace_client():
    dspace_client = dspace.DSpaceClient("mock://example.com/")
    dspace_client.header = {}
    dspace_client.cookies = {}
    dspace_client.user_full_name = ""
    return dspace_client


@pytest.fixture()
def s3_client():
    return boto3.client("s3", region_name="us-east-1")


@pytest.fixture
def mocked_s3_bucket():
    bucket_name = "mocked-bucket"
    with mock_aws():
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket=bucket_name)
        s3.put_object(Body="", Bucket=bucket_name, Key="one-to-one/aaaa_001_01.pdf")
        s3.put_object(
            Body="",
            Bucket=bucket_name,
            Key="one-to-one/aaaa_002_01.pdf",
        )
        s3.put_object(
            Body="",
            Bucket=bucket_name,
            Key="many-to-one/bbbb_003_01.pdf",
        )
        s3.put_object(
            Body="",
            Bucket=bucket_name,
            Key="many-to-one/bbbb_003_02.pdf",
        )
        s3.put_object(
            Body="",
            Bucket=bucket_name,
            Key="many-to-one/bbbb_004_01.pdf",
        )
        s3.put_object(
            Body="",
            Bucket=bucket_name,
            Key="many-to-one/bbbb_003_01.jpg",
        )
        s3.put_object(
            Body="", Bucket=bucket_name, Key="nested/prefix/objects/include_005_01.pdf"
        )
        yield


@pytest.fixture
def mocked_s3_bucket_bitstreams():
    return {
        "001": ["s3://mocked-bucket/one-to-one/aaaa_001_01.pdf"],
        "002": ["s3://mocked-bucket/one-to-one/aaaa_002_01.pdf"],
        "003": [
            "s3://mocked-bucket/many-to-one/bbbb_003_01.jpg",
            "s3://mocked-bucket/many-to-one/bbbb_003_01.pdf",
            "s3://mocked-bucket/many-to-one/bbbb_003_02.pdf",
        ],
        "004": ["s3://mocked-bucket/many-to-one/bbbb_004_01.pdf"],
        "005": ["s3://mocked-bucket/nested/prefix/objects/include_005_01.pdf"],
    }


@pytest.fixture()
def output_dir(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return str(f"{output_dir}/")


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def web_mock():
    with requests_mock.Mocker() as mocked_request:
        # DSpace authentication
        cookies = {"JSESSIONID": "11111111"}
        mocked_request.post("mock://example.com/login", cookies=cookies)
        user_json = {"fullname": "User Name"}
        mocked_request.get("mock://example.com/status", json=user_json)

        # get - retrieve item
        item_get_url = "mock://example.com/items/123?expand=all"
        item_get_response = {"metadata": {"title": "Sample title"}, "type": "item"}
        mocked_request.get(item_get_url, json=item_get_response)

        # get - retrieve uuid from handle
        uuid_get_url = "mock://example.com/handle/111.1111"
        uuid_get_response = {"uuid": "a1b2"}
        mocked_request.get(uuid_get_url, json=uuid_get_response)

        # get - retrieve uuid from handle (for test_cli.test_additems )
        uuid_get_url_2 = "mock://example.com/handle/333.3333"
        uuid_get_response_2 = {"uuid": "k1l2"}
        mocked_request.get(uuid_get_url_2, json=uuid_get_response_2)

        # get - retrieve filtered set of items
        filtered_items_get_url = "mock://example.com/filtered-items?"
        filtered_items_get_response = [
            {"json": {"items": [{"link": "1234"}]}},
            {"json": {"items": []}},
        ]
        mocked_request.get(filtered_items_get_url, filtered_items_get_response)

        # post - add collection to community
        collection_post_url = "mock://example.com/communities/a1b2/collections"
        collection_post_response = {"uuid": "c3d4"}
        mocked_request.post(collection_post_url, json=collection_post_response)

        # post - add item to collection
        item_post_url = "mock://example.com/collections/c3d4/items"
        item_post_response = {"uuid": "e5f6", "handle": "222.2222"}
        mocked_request.post(item_post_url, json=item_post_response)

        # post - add item to collection (for test_cli.test_additems)
        item_post_url_2 = "mock://example.com/collections/k1l2/items"
        item_post_response_2 = {"uuid": "e5f6", "handle": "222.2222"}
        mocked_request.post(item_post_url_2, json=item_post_response_2)

        # post - add bitstream to item
        bitstream_post_url = (
            "mock://example.com/items/e5f6/bitstreams?name=aaaa_001_01.pdf"
        )
        bitstream_post_response = {"uuid": "g7h8"}
        mocked_request.post(bitstream_post_url, json=bitstream_post_response)

        bitstream_post_url_2 = (
            "mock://example.com/items/e5f6/bitstreams?name=aaaa_002_01.pdf"
        )
        bitstream_post_response_2 = {"uuid": "i9j0"}
        mocked_request.post(bitstream_post_url_2, json=bitstream_post_response_2)

        bitstream_post_url_3 = (
            "mock://example.com/items/e5f6/bitstreams?name=bbbb_003_01.jpg"
        )
        bitstream_post_response_3 = {"uuid": "item_003_01_a"}
        mocked_request.post(bitstream_post_url_3, json=bitstream_post_response_3)

        bitstream_post_url_4 = (
            "mock://example.com/items/e5f6/bitstreams?name=bbbb_003_01.pdf"
        )
        bitstream_post_response_4 = {"uuid": "item_003_01_b"}
        mocked_request.post(bitstream_post_url_4, json=bitstream_post_response_4)

        bitstream_post_url_5 = (
            "mock://example.com/items/e5f6/bitstreams?name=bbbb_003_02.pdf"
        )
        bitstream_post_response_5 = {"uuid": "item_003_02_a"}
        mocked_request.post(bitstream_post_url_5, json=bitstream_post_response_5)

        bitstream_post_url_6 = (
            "mock://example.com/items/e5f6/bitstreams?name=bbbb_004_01.pdf"
        )
        bitstream_post_response_6 = {"uuid": "item_004_01_a"}
        mocked_request.post(bitstream_post_url_6, json=bitstream_post_response_6)

        bitstream_post_url_7 = (
            "mock://example.com/items/e5f6/bitstreams?name=include_005_01.pdf"
        )
        bitstream_post_response_7 = {"uuid": "item_005_01_a"}
        mocked_request.post(bitstream_post_url_7, json=bitstream_post_response_7)
        # mocked_request.get("mock://remoteserver.com/files/test_01.pdf", content=b"Sample")

        yield mocked_request
