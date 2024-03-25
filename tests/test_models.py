import attr
from moto import mock_aws

from dsaps.dspace import Bitstream, Collection, Item, MetadataEntry


def test_dspace_client_authenticate(dspace_client):
    email = "test@test.mock"
    password = "1234"
    dspace_client.authenticate(email, password)
    assert dspace_client.user_full_name == "User Name"
    assert dspace_client.cookies == {"JSESSIONID": "11111111"}


def test_filtered_item_search(dspace_client):
    item_links = dspace_client.filtered_item_search(
        key="dc.title", string="test", query_type="contains", selected_collections=""
    )
    assert "1234" in item_links


def test_get_uuid_from_handle(dspace_client):
    id = dspace_client.get_uuid_from_handle("111.1111")
    assert id == "a1b2"


def test_get_record(dspace_client):
    dspace_item = dspace_client.get_record("123", "items")
    assert attr.asdict(dspace_item)["metadata"] == {"title": "Sample title"}


def test_post_bitstream(dspace_client, mocked_s3_bucket):
    item_uuid = "e5f6"
    bitstream = Bitstream(
        name="aaaa_001_01.pdf", file_path="s3://mocked-bucket/one-to-one/aaaa_001_01.pdf"
    )
    bit_uuid = dspace_client.post_bitstream(item_uuid, bitstream)
    assert bit_uuid == "g7h8"


def test_post_collection_to_community(dspace_client):
    comm_handle = "111.1111"
    coll_name = "Test Collection"
    coll_uuid = dspace_client.post_collection_to_community(comm_handle, coll_name)
    assert coll_uuid == "c3d4"


@mock_aws
def test_post_item_to_collection(dspace_client, mocked_s3_bucket):
    item = Item()
    item.bitstreams = [
        Bitstream(name="aaaa_001_01.pdf", file_path="s3://mocked-bucket/aaaa_001_01.pdf")
    ]
    item.metadata = [
        MetadataEntry(key="dc.title", value="Title 1", language="en_US"),
        MetadataEntry(key="dc.contributor.author", value="May Smith", language=None),
    ]
    collection_uuid = "c3d4"
    item_uuid, item_handle = dspace_client.post_item_to_collection(collection_uuid, item)
    assert item_uuid == "e5f6"
    assert item_handle == "222.2222"


def test_populate_class_instance(dspace_client):
    class_type = Collection
    dspace_collection = {"name": "Test title", "type": "collection", "items": []}
    dspace_collection = dspace_client._populate_class_instance(
        class_type, dspace_collection
    )
    assert type(dspace_collection) is class_type
    assert dspace_collection.name == "Test title"


def test_build_uuid_list(dspace_client):
    dspace_items = {"items": [{"uuid": "1234"}]}
    children = "items"
    child_list = dspace_client._build_uuid_list(dspace_items, children)
    assert "1234" in child_list


def test_collection_add_items(source_metadata_csv, source_config):
    collection = Collection.add_items(source_metadata_csv, source_config["mapping"])
    assert len(collection.items) == 5


def test_item_create(source_metadata_csv_with_bitstreams, source_config):
    record = next(source_metadata_csv_with_bitstreams)
    assert attr.asdict(Item.create(record, source_config["mapping"])) == {
        "uuid": None,
        "name": None,
        "handle": None,
        "link": None,
        "type": None,
        "metadata": [
            {"key": "dc.title", "value": "Title 1", "language": "en_US"},
            {"key": "dc.contributor.author", "value": "May Smith", "language": None},
        ],
        "bitstreams": [
            {
                "name": "aaaa_001_01.pdf",
                "file_path": "s3://mocked-bucket/one-to-one/aaaa_001_01.pdf",
            }
        ],
        "item_identifier": "001",
        "source_system_identifier": None,
    }


def test_item_get_ids(source_metadata_csv, source_config):
    record = next(source_metadata_csv)
    assert Item.get_ids(record, source_config["mapping"]) == {"item_identifier": "001"}


def test_item_get_bitstreams(source_metadata_csv_with_bitstreams, source_config):
    record = next(source_metadata_csv_with_bitstreams)
    assert Item.get_bitstreams(record) == [
        Bitstream(
            name="aaaa_001_01.pdf",
            file_path="s3://mocked-bucket/one-to-one/aaaa_001_01.pdf",
        )
    ]


def test_item_get_metadata(source_metadata_csv, source_config):
    record = next(source_metadata_csv)
    metadata = Item.get_metadata(record, source_config["mapping"])
    assert [attr.asdict(m) for m in metadata] == [
        {"key": "dc.title", "value": "Title 1", "language": "en_US"},
        {"key": "dc.contributor.author", "value": "May Smith", "language": None},
    ]
