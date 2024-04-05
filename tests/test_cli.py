from moto import mock_aws

from dsaps.cli import main


@mock_aws
def test_additems(runner, mocked_s3_bucket, caplog):
    """Test adding items to a collection."""
    result = runner.invoke(
        main,
        [
            "--config-file",
            "tests/fixtures/source_config.json",
            "--url",
            "mock://example.com/",
            "--email",
            "test@test.mock",
            "--password",
            "1234",
            "additems",
            "--metadata-csv",
            "tests/fixtures/updated-source_metadata.csv",
            "--content-directory",
            "s3://mocked-bucket",
            "--collection-handle",
            "333.3333",
        ],
    )
    assert result.exit_code == 0

    result = runner.invoke(
        main,
        [
            "--config-file",
            "tests/fixtures/source_config.json",
            "--url",
            "mock://example.com/",
            "--email",
            "test@test.mock",
            "--password",
            "1234",
            "newcollection",
            "--community-handle",
            "111.1111",
            "--collection-name",
            "Test Collection",
            "additems",
            "--metadata-csv",
            "tests/fixtures/updated-source_metadata.csv",
            "--content-directory",
            "s3://mocked-bucket",
        ],
    )
    assert result.exit_code == 0


def test_newcollection(runner):
    """Test newcoll command."""
    result = runner.invoke(
        main,
        [
            "--config-file",
            "tests/fixtures/source_config.json",
            "--url",
            "mock://example.com/",
            "--email",
            "test@test.mock",
            "--password",
            "1234",
            "newcollection",
            "--community-handle",
            "111.1111",
            "--collection-name",
            "Test Collection",
        ],
    )
    assert result.exit_code == 0


@mock_aws
def test_reconcile(runner, mocked_s3_bucket, output_dir):
    """Test reconcile command."""
    result = runner.invoke(
        main,
        [
            "--config-file",
            "tests/fixtures/source_config.json",
            "--url",
            "mock://example.com/",
            "--email",
            "test@test.mock",
            "--password",
            "1234",
            "reconcile",
            "--metadata-csv",
            "tests/fixtures/source_metadata.csv",
            "--output-directory",
            output_dir,
            "--content-directory",
            "s3://mocked-bucket",
        ],
    )
    assert result.exit_code == 0
