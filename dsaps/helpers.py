import ast
import csv
import os
import re
import yaml

import smart_open


S3_BUCKET_REGEX = re.compile(r"^([^\/]*)")
S3_PREFIX_REGEX = re.compile(r"(?<=\/)(.*)")


def load_source_config(config_file: str):
    with smart_open.open(config_file, "r") as file:
        return yaml.safe_load(file)


def create_csv_from_list(list_name, output):
    """Create CSV file from list."""
    with open(f"{output}.csv", "w") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["id"])
        for item in list_name:
            writer.writerow([item])


def get_files_from_s3(
    s3_path: str,
    s3_client,
    id_regex: str,
    bitstream_folders=None,
) -> dict:
    """Get a list of files on S3 per unique item identifier.

    Args:
        s3_path (str): S3 path to the topmost level directory in which to look for files.
            Formatted as "s3://bucket/prefix/" or "bucket/prefix/".
        s3_client (_type_): S3 client.
        id_regex (str): A regex expression for extracting the item identifier
            from the S3 file object key.
        bitstream_folders (list[str], optional): A list of subfolders in which to look for bitstreams.
            If any of the subfolders are found in the S3 file object key for the bitstream, the file
            object key is included in the returned output. Defaults to None.

    Returns:
        dict: A dictionary where keys denote unique item identifiers and values are a list of
            S3 file object keys associated with the item identifier.
    """
    files = {}
    s3_path = s3_path.removeprefix("s3://")
    bucket = parse_value_from_text(s3_path, S3_BUCKET_REGEX)
    operation_parameters = {"Bucket": bucket}
    if prefix := parse_value_from_text(s3_path, S3_PREFIX_REGEX):
        operation_parameters.update({"Prefix": prefix})

    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(**operation_parameters):
        for file in page["Contents"]:
            file_path = f"s3://{bucket}/{file['Key']}"
            file_name = file_path.split("/")[-1]
            if bitstream_folders:
                # if the object is not stored in any of the folders specified
                # exclude object
                if not [folder for folder in bitstream_folders if folder in file_path]:
                    continue
            item_identifier = parse_value_from_text(file_name, id_regex)
            files.setdefault(item_identifier, []).append(file_path)
    for key, value in files.items():
        files[key] = sorted(
            value, key=lambda x: x.split(parse_value_from_text(x, id_regex))[1]
        )
    return dict(sorted(files.items()))


def parse_value_from_text(
    text: str,
    regex: str,
):
    pattern = re.compile(regex)
    if matches := pattern.findall(text):
        return matches[0]


def create_ingest_report(items, file_name):
    """Create ingest report that matches external systems' identifiers with newly
    created DSpace handles."""
    with open(f"{file_name}", "w") as writecsv:
        writer = csv.writer(writecsv)
        writer.writerow(["uri", "link"])
        for item in items:
            writer.writerow(
                [item.source_system_identifier]
                + [f"https://hdl.handle.net/{item.handle}"]
            )


def create_metadata_id_list(metadata_csv):
    """Create list of IDs from a metadata CSV."""
    metadata_ids = []
    with open(metadata_csv) as csvfile:
        reader = csv.DictReader(csvfile)
        metadata_ids = [
            row["item_identifier"] for row in reader if row["item_identifier"] != ""
        ]
    return metadata_ids


def match_files_to_metadata(file_list, metadata_ids):
    """Create list of files matched to metadata records."""
    file_matches = [
        file_id
        for metadata_id in metadata_ids
        for file_id in file_list
        if file_id == metadata_id
    ]
    return file_matches


def match_metadata_to_files(file_list, metadata_ids):
    """Create list of metadata records matched to files."""
    metadata_matches = [
        metadata_id
        for file_id in file_list
        for metadata_id in metadata_ids
        if file_id == metadata_id
    ]
    return metadata_matches


def update_metadata_csv(metadata_csv, output_directory, metadata_matches, files_dict):
    """Create an updated CSV of only metadata records that have matching files."""
    with open(metadata_csv) as csvfile:
        reader = csv.DictReader(csvfile)
        upd_md_file_name = f"updated-{os.path.basename(metadata_csv)}"
        with open(f"{output_directory}{upd_md_file_name}", "w") as updated_csv:
            fieldnames = [*reader.fieldnames, "bitstreams"]
            writer = csv.DictWriter(updated_csv, fieldnames=fieldnames)
            writer.writeheader()
            for row in reader:
                if row["item_identifier"] in metadata_matches:
                    row["bitstreams"] = files_dict[row["item_identifier"]]
                    writer.writerow(row)
