import csv
import datetime
import logging
import os

from datetime import timedelta
from time import perf_counter

import click
import structlog

from dsaps import dspace, helpers
from dsaps.s3 import S3Client


logger = structlog.get_logger()


def validate_path(ctx, param, value):
    """Validates the formatting of the submitted path"""
    if value[-1] == "/":
        return value
    else:
        raise click.BadParameter("Include / at the end of the path.")


@click.group(chain=True)
@click.option(
    "--config-file",
    envvar="CONFIG_FILE",
    required=True,
    help="File path to source configuration JSON with settings for bitstream retrieval and field mappings.",
)
@click.option(
    "--url",
    envvar="DSPACE_URL",
    required=False,
    help="The url for the DSpace REST API. Defaults to env var DSPACE_URL if not set.",
)
@click.option(
    "-e",
    "--email",
    envvar="DSPACE_EMAIL",
    required=False,
    help=(
        "The email associated with the DSpace user account used for authentication. "
        "Defaults to env var DSPACE_EMAIL if not set."
    ),
)
@click.option(
    "-p",
    "--password",
    envvar="DSPACE_PASSWORD",
    required=False,
    hide_input=True,
    help=(
        "The password associated with the DSpace user account used for authentication. "
        "Defaults to env var DSPACE_PASSWORD if not set."
    ),
)
@click.pass_context
def main(ctx, config_file, url, email, password):
    ctx.obj = {}
    if os.path.isdir("logs") is False:
        os.mkdir("logs")
    dt = datetime.datetime.utcnow().isoformat(timespec="seconds")
    log_suffix = f"{dt}.log"
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    logging.basicConfig(
        format="%(asctime)s %(message)s",
        handlers=[logging.FileHandler(f"logs/log-{log_suffix}", "w")],
        level=logging.INFO,
    )
    logger.info("Running process")
    source_config = helpers.load_source_config(config_file)
    if url:
        dspace_client = dspace.DSpaceClient(url)
        dspace_client.authenticate(email, password)
        ctx.obj["dspace_client"] = dspace_client
    ctx.obj["source_config"] = source_config
    logger.info("Initializing S3 client")
    ctx.obj["s3_client"] = S3Client.get_client()
    ctx.obj["start_time"] = perf_counter()


@main.command()
@click.option(
    "-m",
    "--metadata-csv",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="File path to a CSV file describing the metadata and bitstreams for DSpace uploads.",
)
@click.option(
    "-d",
    "--content-directory",
    required=True,
    help="The name of the S3 bucket containing files for DSpace uploads.",
)
@click.option(
    "-r",
    "--ingest-report",
    is_flag=True,
    help="Create ingest report for updating other systems.",
)
@click.option(
    "-c",
    "--collection-handle",
    help="The handle identifying a DSpace collection into which uploads are deposited.",
    default=None,
)
@click.pass_context
def additems(
    ctx,
    metadata_csv,
    content_directory,
    ingest_report,
    collection_handle,
):
    """Add items to a DSpace collection.

    The updated metadata CSV file from running 'reconcile' is used for this process.
    The method will first add an item to the specified DSpace collection. The bitstreams
    (i.e., files) associated with the item are read from the metadata CSV file, and
    uploaded to the newly created item on DSpace.
    """
    mapping = ctx.obj["source_config"]["mapping"]
    dspace_client = ctx.obj["dspace_client"]

    if "collection_uuid" not in ctx.obj and collection_handle is None:
        raise click.UsageError(
            "Option '--collection-handle' must be used or "
            "run 'additems' after 'newcollection' command."
        )
    elif "collection_uuid" in ctx.obj:
        collection_uuid = ctx.obj["collection_uuid"]
    else:
        collection_uuid = dspace_client.get_uuid_from_handle(collection_handle)

    if metadata_csv is None:
        raise click.UsageError("Option '--metadata-csv' must be used.")

    dspace_collection = dspace.Collection(uuid=collection_uuid)

    with open(metadata_csv, "r") as csvfile:
        metadata = csv.DictReader(csvfile)
        dspace_collection = dspace_collection.add_items(metadata, mapping)

    for item in dspace_collection.items:
        logger.info(f"Posting item: {item}")
        item_uuid, item_handle = dspace_client.post_item_to_collection(
            collection_uuid, item
        )
        item.uuid = item_uuid
        item.handle = item_handle
        logger.info(f"Item posted: {item_uuid}")
        for bitstream in item.bitstreams:
            logger.info(f"Posting bitstream: {bitstream}")
            dspace_client.post_bitstream(item.uuid, bitstream)

    logger.info(
        "Total elapsed: %s",
        str(timedelta(seconds=perf_counter() - ctx.obj["start_time"])),
    )


@main.command()
@click.option(
    "-c",
    "--community-handle",
    required=True,
    help="The handle identifying a DSpace community in which a new collection is created.",
)
@click.option(
    "-n",
    "--collection-name",
    required=True,
    help="The name assigned to the DSpace collection being created.",
)
@click.pass_context
def newcollection(ctx, community_handle, collection_name):
    """Create a new DSpace collection within a community."""
    dspace_client = ctx.obj["dspace_client"]
    collection_uuid = dspace_client.post_collection_to_community(
        community_handle, collection_name
    )
    ctx.obj["collection_uuid"] = collection_uuid


@main.command()
@click.option(
    "-m",
    "--metadata-csv",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="The filepath to a CSV file containing metadata for Dspace uploads.",
)
@click.option(
    "-o",
    "--output-directory",
    default=f"{os.getcwd()}/",
    callback=validate_path,
    help="The filepath where output files are written.",
)
@click.option(
    "-d",
    "--content-directory",
    required=True,
    help="The name of the S3 bucket containing files for DSpace uploads.",
)
@click.pass_context
def reconcile(ctx, metadata_csv, output_directory, content_directory):
    """Match files in the content directory with entries in the metadata CSV file.

    Running this method creates the following CSV files:

        * metadata_matches.csv: File identifiers for entries in metadata CSV file with a
        corresponding file in the content directory.

        * no_files.csv: File identifiers for entries in metadata CSV file without a
        corresponding file in the content directory.

        * no_metadata.csv: File identifiers for files in the content directory without a
        corresponding entry in the metadata CSV file.

        * updated-<metadata-csv>.csv: Entries from the metadata CSV file with a
        corresponding file in the content directory.
    """
    source_settings = ctx.obj["source_config"]["settings"]
    bitstreams = helpers.get_files_from_s3(
        s3_path=content_directory,
        s3_client=ctx.obj["s3_client"],
        bitstream_folders=source_settings.get("bitstream_folders"),
        id_regex=source_settings["id_regex"],
    )
    metadata_ids = helpers.create_metadata_id_list(metadata_csv)
    metadata_matches = helpers.match_metadata_to_files(bitstreams.keys(), metadata_ids)
    file_matches = helpers.match_files_to_metadata(bitstreams.keys(), metadata_ids)
    no_files = set(metadata_ids) - set(metadata_matches)
    no_metadata = set(bitstreams.keys()) - set(file_matches)
    helpers.create_csv_from_list(no_metadata, f"{output_directory}no_metadata")
    helpers.create_csv_from_list(no_files, f"{output_directory}no_files")
    helpers.create_csv_from_list(metadata_matches, f"{output_directory}metadata_matches")
    helpers.update_metadata_csv(
        metadata_csv, output_directory, metadata_matches, bitstreams
    )
