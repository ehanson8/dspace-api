from __future__ import annotations

import ast
import attr
import operator
import requests
import structlog

import smart_open

from attrs import field, define


logger = structlog.get_logger()
op = operator.attrgetter("name")


class DSpaceClient:
    def __init__(self, url):
        header = {"content-type": "application/json", "accept": "application/json"}
        self.url = url.rstrip("/")
        self.cookies = None
        self.header = header
        logger.info("Initializing DSpace client")

    def authenticate(self, email, password):
        """Authenticate user to DSpace API."""
        header = self.header
        data = {"email": email, "password": password}
        session = requests.post(
            f"{self.url}/login", headers=header, params=data, timeout=30
        ).cookies["JSESSIONID"]
        cookies = {"JSESSIONID": session}
        status = requests.get(
            f"{self.url}/status", headers=header, cookies=cookies, timeout=30
        ).json()
        self.user_full_name = status["fullname"]
        self.cookies = cookies
        self.header = header
        logger.info(f"Authenticated to {self.url} as " f"{self.user_full_name}")

    def filtered_item_search(self, key, string, query_type, selected_collections=""):
        """Perform a search against the filtered items endpoint."""
        offset = 0
        items = ""
        item_links = []
        while items != []:
            endpoint = f"{self.url}/filtered-items?"
            params = {
                "query_field[]": key,
                "query_op[]": query_type,
                "query_val[]": string,
                "&collSel[]": selected_collections,
                "limit": 200,
                "offset": offset,
            }
            logger.info(params)
            response = requests.get(
                endpoint,
                headers=self.header,
                params=params,
                cookies=self.cookies,
                timeout=30,
            )
            logger.info(f"Response url: {response.url}")
            response = response.json()
            items = response["items"]
            for item in items:
                item_links.append(item["link"])
            offset = offset + 200
        return item_links

    def get_uuid_from_handle(self, handle):
        """Get UUID for an object based on its handle."""
        hdl_endpoint = f"{self.url}/handle/{handle}"
        record = requests.get(
            hdl_endpoint, headers=self.header, cookies=self.cookies, timeout=30
        ).json()
        return record["uuid"]

    def get_record(self, uuid, record_type):
        """Get an individual record of a specified type."""
        url = f"{self.url}/{record_type}/{uuid}?expand=all"
        record = requests.get(
            url, headers=self.header, cookies=self.cookies, timeout=30
        ).json()
        if record_type == "items":
            dspace_object = self._populate_class_instance(Item, record)
        elif record_type == "communities":
            dspace_object = self._populate_class_instance(Community, record)
        elif record_type == "collections":
            dspace_object = self._populate_class_instance(Collection, record)
        else:
            logger.info("Invalid record type.")
            exit()
        return dspace_object

    def post_bitstream(self, item_uuid, bitstream):
        """Post a bitstream to a specified item and return the bitstream
        ID."""
        endpoint = f"{self.url}/items/{item_uuid}/bitstreams?name={bitstream.name}"
        header_upload = {"accept": "application/json"}
        logger.info(endpoint)
        with smart_open.open(bitstream.file_path, "rb") as data:
            post_response = requests.post(
                endpoint,
                headers=header_upload,
                cookies=self.cookies,
                data=data,
                timeout=30,
            )
            logger.info(f"Bitstream POST status: {post_response}")
            response = post_response.json()
            logger.info(f"Bitstream POST response: {response}")
            bitstream_uuid = response["uuid"]
            return bitstream_uuid

    def post_collection_to_community(self, comm_handle, coll_name):
        """Post a collection to a specified community."""
        hdl_endpoint = f"{self.url}/handle/{comm_handle}"
        community = requests.get(
            hdl_endpoint, headers=self.header, cookies=self.cookies, timeout=30
        ).json()
        comm_uuid = community["uuid"]
        uuid_endpoint = f"{self.url}/communities/{comm_uuid}/collections"
        coll_uuid = requests.post(
            uuid_endpoint,
            headers=self.header,
            cookies=self.cookies,
            json={"name": coll_name},
            timeout=30,
        ).json()
        coll_uuid = coll_uuid["uuid"]
        logger.info(f"Collection posted: {coll_uuid}")
        return coll_uuid

    def post_item_to_collection(self, collection_uuid, item):
        """Post item to a specified collection and return the item ID."""
        endpoint = f"{self.url}/collections/{collection_uuid}/items"
        logger.info(endpoint)
        post_resp = requests.post(
            endpoint,
            headers=self.header,
            cookies=self.cookies,
            json={"metadata": attr.asdict(item)["metadata"]},
            timeout=30,
        )
        logger.info(f"Item POST status: {post_resp}")
        post_response = post_resp.json()
        logger.info(f"Item POST response: {post_response}")
        item_uuid = post_response["uuid"]
        item_handle = post_response["handle"]
        return item_uuid, item_handle

    def _populate_class_instance(self, class_type, record):
        """Populate class instance with data from record."""
        fields = [op(field) for field in attr.fields(class_type)]
        kwargs = {k: v for k, v in record.items() if k in fields}
        kwargs["type"] = record["type"]
        if class_type == Community:
            collections = self._build_uuid_list(record, kwargs, "collections")
            kwargs["collections"] = collections
        elif class_type == Collection:
            items = self._build_uuid_list(record, "items")
            kwargs["items"] = items
        return class_type(**kwargs)

    def _build_uuid_list(self, record, children):
        """Build list of the uuids of the object's children."""
        child_list = []
        for child in record[children]:
            child_list.append(child["uuid"])
        return child_list


@define
class Bitstream:
    name = field(default=None)
    file_path = field(default=None)


@define
class MetadataEntry:
    key = field(default=None)
    value = field(default=None)
    language = field(default=None)


@define
class Object:
    uuid = field(default=None)
    name = field(default=None)
    handle = field(default=None)
    link = field(default=None)
    type = field(default=None)


@define
class Item(Object):
    metadata = field(factory=list)
    bitstreams = field(factory=list)
    item_identifier = field(default=None)
    source_system_identifier = field(default=None)

    @classmethod
    def create(cls, record, mapping) -> Item:
        return cls(
            metadata=cls.get_metadata(record, mapping),
            bitstreams=cls.get_bitstreams(record),
            **cls.get_ids(record, mapping),
        )

    @classmethod
    def get_bitstreams(cls, record) -> list:
        if _bitstreams := record.get("bitstreams"):
            bitstreams = []
            for file_path in ast.literal_eval(_bitstreams):
                file_name = file_path.split("/")[-1]
                bitstreams.append(Bitstream(name=file_name, file_path=file_path))
            return bitstreams

    @classmethod
    def get_ids(cls, record, mapping) -> dict:
        ids = {}
        if item_id_mapping := mapping.get("item_identifier"):
            ids["item_identifier"] = record.get(item_id_mapping["csv_field_name"])
        if source_system_id_mapping := mapping.get("source_system_identifier"):
            ids["source_system_identifier"] = record.get(
                source_system_id_mapping["csv_field_name"]
            )
        return ids

    @classmethod
    def get_metadata(cls, record, mapping) -> list:
        """Create metadata for an item based on a CSV row and a JSON mapping field map."""
        metadata = []
        for field_name, field_mapping in mapping.items():
            if field_name not in ["item_identifier", "source_system_identifier"]:

                field_value = record[field_mapping["csv_field_name"]]

                if field_value:
                    delimiter = field_mapping["delimiter"]
                    language = field_mapping["language"]
                    if delimiter:
                        metadata.extend(
                            [
                                MetadataEntry(
                                    key=field_name,
                                    value=value,
                                    language=language,
                                )
                                for value in field_value.split(delimiter)
                            ]
                        )
                    else:
                        metadata.append(
                            MetadataEntry(
                                key=field_name,
                                value=field_value,
                                language=language,
                            )
                        )
        return metadata


@define
class Collection(Object):
    items = field(factory=list)

    @classmethod
    def add_items(cls, csv_reader, field_map) -> Collection:
        """Create metadata for the collection's items based on a CSV and a JSON mapping
        field map."""
        items = [Item.create(row, field_map) for row in csv_reader]
        return cls(items=items)


@define
class Community(Object):
    collections = field(default=None)
