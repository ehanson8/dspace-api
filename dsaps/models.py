from functools import partial
import glob
import operator
import os

import attr
import requests
import structlog

Field = partial(attr.ib, default=None)
Group = partial(attr.ib, default=[])

logger = structlog.get_logger()
op = operator.attrgetter('name')


class Client:
    def __init__(self, url):
        header = {'content-type': 'application/json', 'accept':
                  'application/json'}
        self.url = url.rstrip('/')
        self.cookies = None
        self.header = header
        logger.info('Initializing client')

    def authenticate(self, email, password):
        """Authenticate user to DSpace API."""
        header = self.header
        data = {'email': email, 'password': password}
        session = requests.post(f'{self.url}/login', headers=header,
                                params=data).cookies['JSESSIONID']
        cookies = {'JSESSIONID': session}
        status = requests.get(f'{self.url}/status', headers=header,
                              cookies=cookies).json()
        self.user_full_name = status['fullname']
        self.cookies = cookies
        self.header = header
        logger.info(f'Authenticated to {self.url} as 'f'{self.user_full_name}')

    def filtered_item_search(self, key, string, query_type,
                             selected_collections=''):
        """Performs a search against the filtered items endpoint."""
        offset = 0
        items = ''
        item_links = []
        while items != []:
            endpoint = f'{self.url}/filtered-items?'
            params = {'query_field[]': key, 'query_op[]': query_type,
                      'query_val[]': string, '&collSel[]':
                      selected_collections, 'limit': 200, 'offset': offset}
            logger.info(params)
            response = requests.get(endpoint, headers=self.header,
                                    params=params, cookies=self.cookies)
            logger.info(f'Response url: {response.url}')
            response = response.json()
            items = response['items']
            for item in items:
                item_links.append(item['link'])
            offset = offset + 200
        return item_links

    def get_id_from_handle(self, handle):
        """Retrieves UUID for an object based on its handle."""
        hdl_endpoint = f'{self.url}/handle/{handle}'
        rec_obj = requests.get(hdl_endpoint, headers=self.header,
                               cookies=self.cookies).json()
        return rec_obj['uuid']

    def get_record(self, uuid, rec_type):
        """Retrieve an individual record of a particular type."""
        url = f'{self.url}/{rec_type}/{uuid}?expand=all'
        record = requests.get(url, headers=self.header,
                              cookies=self.cookies).json()
        if rec_type == 'items':
            rec_obj = self._pop_inst(Item, record)
        elif rec_type == 'communities':
            rec_obj = self._pop_inst(Community, record)
        elif rec_type == 'collections':
            rec_obj = self._pop_inst(Collection, record)
        else:
            logger.info('Invalid record type.')
            exit()
        return rec_obj

    def post_bitstream(self, item_id, bitstream):
        """Posts a bitstream to a specified item and returns the bitstream
        ID."""
        endpoint = (f'{self.url}/items/{item_id}'
                    f'/bitstreams?name={bitstream.name}')
        header_upload = {'accept': 'application/json'}
        data = open(bitstream.file_path, 'rb')
        response = requests.post(endpoint, headers=header_upload,
                                 cookies=self.cookies, data=data).json()
        bitstream_id = response['uuid']
        return bitstream_id

    def post_coll_to_comm(self, comm_handle, coll_name):
        """Posts a collection to a specified community."""
        hdl_endpoint = f'{self.url}/handle/{comm_handle}'
        community = requests.get(hdl_endpoint, headers=self.header,
                                 cookies=self.cookies).json()
        comm_id = community['uuid']
        uuid_endpoint = f'{self.url}/communities/{comm_id}/collections'
        coll_id = requests.post(uuid_endpoint, headers=self.header,
                                cookies=self.cookies,
                                json={'name': coll_name}).json()
        coll_id = coll_id['uuid']
        logger.info(f'Collection posted: {coll_id}')
        return coll_id

    def post_item_to_collection(self, collection_id, item):
        """Posts item to a specified collection and returns the item ID."""
        endpoint = f'{self.url}/collections/{collection_id}/items'
        post_response = requests.post(
            endpoint, headers=self.header, cookies=self.cookies,
            json={'metadata': attr.asdict(item)['metadata']}).json()
        item_id = post_response['uuid']
        item.handle = post_response['handle']
        return item_id

    def _pop_inst(self, class_type, rec_obj):
        """Populate class instance with data from record."""
        fields = [op(field) for field in attr.fields(class_type)]
        kwargs = {k: v for k, v in rec_obj.items() if k in fields}
        kwargs['objtype'] = rec_obj['type']
        if class_type == Community:
            collections = self._build_uuid_list(rec_obj, kwargs, 'collections')
            rec_obj['collections'] = collections
        elif class_type == Collection:
            items = self._build_uuid_list(rec_obj, 'items')
            rec_obj['items'] = items
        rec_obj = class_type(**kwargs)
        return rec_obj

    def _build_uuid_list(self, rec_obj, children):
        """Builds a list of the uuids for an object's children."""
        child_list = []
        for child in rec_obj[children]:
            child_list.append(child['uuid'])
        return child_list


@attr.s
class BaseRecord:
    uuid = Field()
    name = Field()
    handle = Field()
    link = Field()
    objtype = Field()


@attr.s
class Collection(BaseRecord):
    items = Group()

    def post_items(self, client):
        for item in self.items:
            item_id = client.post_item_to_collection(self.uuid, item)
            item.uuid = item_id
            logger.info(f'Item posted: {item_id}')
            for bitstream in item.bitstreams:
                bitstream_id = client.post_bitstream(item_id, bitstream)
                logger.info(f'Bitstream posted: {bitstream_id}')
            yield item

    @classmethod
    def from_csv(cls, csv_reader, field_map):
        items = [
            Item.from_row(row, field_map) for row in csv_reader
            ]
        return cls(items=items)


@attr.s
class Community(BaseRecord):
    collections = Field()


@attr.s
class Item(BaseRecord):
    metadata = Group()
    bitstreams = Group()
    file_identifier = Field()
    source_system_identifier = Field()

    def bitstreams_from_directory(self, directory, file_type='*'):
        files = glob.iglob(
            f'{directory}/**/{self.file_identifier}*.{file_type}',
            recursive=True
            )
        file_list = []
        for file in files:
            file_list.append(file)
        file_list.sort()
        self.bitstreams = [
            Bitstream(name=os.path.basename(f),
                      file_path=f) for f in file_list
            ]

    @classmethod
    def from_row(cls, row, field_map):
        metadata = []
        for f in field_map:
            field = row[field_map[f]['csv_field_name']]
            if f == 'file_identifier':
                file_identifier = field
                continue  # file_identifier is not included in DSpace metadata
            if f == 'dc.relation.isversionof':
                source_system_identifier = field
            delimiter = field_map[f]['delimiter']
            language = field_map[f]['language']
            if delimiter:
                metadata.extend([
                    MetadataEntry(key=f, value=v, language=language)
                    for v in field.split(delimiter)
                    ])
            else:
                metadata.append(
                    MetadataEntry(key=f, value=field, language=language)
                    )
        return cls(metadata=metadata, file_identifier=file_identifier,
                   source_system_identifier=source_system_identifier)


@attr.s
class Bitstream():
    name = Field()
    file_path = Field()


@attr.s
class MetadataEntry():
    key = Field()
    value = Field()
    language = Field()
