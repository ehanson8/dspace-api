import attr

from dsaps import models


def test_authenticate(client):
    """Test authenticate method."""
    email = 'test@test.mock'
    password = '1234'
    client.authenticate(email, password)
    assert client.user_full_name == 'User Name'
    assert client.cookies == {'JSESSIONID': '11111111'}


def test_filtered_item_search(client):
    """Test filtered_item_search method."""
    key = 'dc.title'
    string = 'test'
    query_type = 'contains'
    item_links = client.filtered_item_search(key, string, query_type,
                                             selected_collections='')
    assert '1234' in item_links


def test_get_id_from_handle(client):
    """Test get_id_from_handle method."""
    id = client.get_id_from_handle('111.1111')
    assert id == 'a1b2'


def test_get_record(client):
    """Test get_record method."""
    rec_obj = client.get_record('123', 'items')
    assert attr.asdict(rec_obj)['metadata'] == {'title': 'Sample title'}


def test_post_bitstream(client, input_dir):
    """Test post_bitstream method."""
    item_id = 'e5f6'
    bitstream = open(f'{input_dir}test_01.pdf', 'rb')
    bit_id = client.post_bitstream(item_id, bitstream)
    assert 'g7h8' == bit_id


def test_post_coll_to_comm(client):
    """Test post_coll_to_comm method."""
    comm_handle = '111.1111'
    coll_name = 'Test Collection'
    coll_id = client.post_coll_to_comm(comm_handle, coll_name)
    assert coll_id == 'c3d4'


def test_post_item_to_coll(client, input_dir):
    """Test post_items_to_coll method."""
    item = models.Item()
    item_metadata = {"metadata": [
                     {"key": "file_identifier",
                      "value": "test"},
                     {"key": "dc.title", "value":
                      "Monitoring Works: Getting Teachers",
                      "language": "en_US"},
                     {"key": "dc.relation.isversionof",
                      "value": "repo/0/ao/123"}]}
    item.bitstreams = [open(f'{input_dir}test_01.pdf', 'rb')]
    item.metadata = item_metadata
    coll_id = 'c3d4'
    ingest_type = 'local'
    ingest_report_id = '/repo/0/ao/123'
    item_id = client.post_item_to_coll(coll_id, item, {}, ingest_type,
                                       ingest_report_id)
    assert 'e5f6' == item_id


def test__pop_inst(client):
    """Test _pop_inst method."""
    class_type = models.Collection
    rec_obj = {'name': 'Test title', 'type': 'collection', 'items': []}
    rec_obj = client._pop_inst(class_type, rec_obj)
    assert type(rec_obj) == class_type
    assert rec_obj.name == 'Test title'


def test__build_uuid_list(client):
    """Test _build_uuid_list method."""
    rec_obj = {'items': [{'uuid': '1234'}]}
    children = 'items'
    child_list = client._build_uuid_list(rec_obj, children)
    assert '1234' in child_list
