import threading
import logging
import pprint
import gc

from elasticsearch.helpers import bulk, BulkIndexError
from elasticsearch import Elasticsearch
from elasticsearch import exceptions
import elasticsearch.dsl as dsl

from django.conf import settings
from django.apps import apps
from django.db import models

from .utils import merge
from .fields import FieldMappingMixin, KitchenSinkField

logger = logging.getLogger(__name__)

CACHE = threading.local()
CHUNKSIZE = 1000


def get_client(connection):
    es_client = getattr(CACHE, 'es_client', None)
    if es_client is None:
        config = settings.ELASTICSEARCH_CONNECTIONS[connection]
        (host_list, options) = (config.get('HOSTS', []),
                                config.get('CONNECTION_OPTIONS', {}))
        es_client = Elasticsearch(hosts=host_list, **options)
        setattr(CACHE, 'es_client', es_client)

    return es_client


def queryset_iterator(queryset, chunksize=CHUNKSIZE):
    """
    Iterate over a Django Queryset ordered by the primary key

    This method loads a maximum of chunksize (default: 1000) rows in it's
    memory at the same time while django normally would load all rows in it's
    memory. Using the iterator() method only causes it to not preload all the
    classes.

    Note that this implementation does not support ordered query sets.

    Taken from: http://djangosnippets.org/snippets/1949/
    """
    assert queryset.exists(), "Can't iterate over empty queryset"

    ordering = queryset.model._meta.pk.get_attname()
    pk = getattr(queryset.order_by('-{}'.format(ordering))[0], ordering) + 1
    last_pk = getattr(queryset.order_by(ordering)[0], ordering)

    queryset = queryset.order_by('-{}'.format(ordering))
    total = 0
    while pk > last_pk:
        chunk = queryset.filter(pk__lt=pk)[:chunksize]
        pk = getattr(chunk[len(chunk) - 1], ordering)
        total += len(chunk)
        yield chunk

        log_msg = "Visited {} records, {} remaining"
        logger.info(log_msg.format(total, queryset.filter(pk__lt=pk).count()))
        gc.collect()

    logger.info("Iterated {} records".format(total))


class TypeAwareSerializableHit(dsl.response.Hit):
    def __init__(self, document, search_meta):
        super().__init__(document)

        for name, field in search_meta.get_fields().items():
            if name not in self:
                continue

            self[name] = field.to_python(self[name])

            # Support query result serialization (e.g., JSON) by translating
            # non-native utility types 'AttrList', 'AttrDict'.
            if isinstance(self[name], dsl.utils.AttrList):
                self[name] = self[name]._l_
            elif isinstance(self[name], dsl.utils.AttrDict):
                self[name] = self[name]._d_

    @classmethod
    def make_callback(cls, search_meta):
        def callback(document):
            return cls(document, search_meta)
        callback._matches = lambda x: True
        return callback


class Search(FieldMappingMixin):
    connection = getattr(settings, 'ELASTICSEARCH_DEFAULT_CONNECTION', 'default')
    handler = getattr(settings, 'ELASTICSEARCH_INDEX_HANDLER', None)

    date_field = 'modified_on'

    # A dictionary whose keys are other models that this model's index
    # depends on, and whose values are query set paramaters for this model
    # to select the instances that depend on an instance of the key model.
    # For example, the index for BlogPost might use information from Author,
    # so it would have dependencies = {Author: 'author'}.
    # When an Author is saved, this causes BlogPost's returned by the query
    # BlogPost.objects.filter(author=instance) to be re-indexed.
    dependencies = {}

    # By default, an index update will determine whether or not additional
    # indexes are related to a given record and will dispatch updates
    # according to the relationships described in 'get_dependencies()'.
    #
    # To disable this behavior, set the following attribute to False.
    #
    # To extend or otherwise change this behavior, override the interface
    # method 'should_dispatch_dependencies'.
    dispatch_dependencies = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.client = get_client(self.connection)

    @classmethod
    def bind_to_model(cls, model):
        setattr(model, 'Search', cls)

    @classmethod
    def as_field(cls, attr, model, field_type, source_fields=None, use_all_field=None):
        class _inner(field_type):
            mapping_type = 'object'

        def _filter_fields(fields):
            if source_fields is None:
                return fields
            if isinstance(fields, list):
                return [f for f in fields if f in source_fields]
            if isinstance(fields, dict):
                return dict([
                    (k, v) for k,v in fields.items() if k in source_fields
                ])

        field = _inner(
            attr,
            model=model,
            attribute_fields=_filter_fields(cls.attribute_fields),
            template_fields=_filter_fields(cls.template_fields),
            other_fields=_filter_fields(cls.other_fields)
        )
        field.use_all_field = (
            cls.use_all_field if use_all_field is None else use_all_field
        )
        return field

    def get_settings(self):
        field_settings = super().get_settings()
        if self.use_all_field:
            field_settings = merge([field_settings,
                                    KitchenSinkField().get_field_settings()])
        return field_settings

    def get_mapping(self):
        mapping = super().get_mapping()
        if self.use_all_field:
            all_field = KitchenSinkField().get_field_mapping()
            mapping['properties'][self.all_field_name] = all_field
        return mapping

    def get_index(self):
        index_name = settings.ELASTICSEARCH_CONNECTIONS[self.connection]['INDEX_NAME']
        return '{}--{}'.format(index_name, self.get_doc_type())

    def get_doc_type(self):
        return "{}_{}".format(self.model._meta.app_label, self.model._meta.model_name)

    def get_field_type(self, fieldname):
        mapping = self.get_mapping()
        for field in fieldname.split('.'):
            mapping = mapping['properties'].get(field, None)
            if mapping is None:
                return None

        return mapping['type']

    def has_index_changed(self, instance, fields=None):
        """
        Evaluates whether any indexed fields have changed on instance.
        """
        index_entry = self.get_entry_mapping(instance)
        if index_entry is None:
            logger.debug(
                "No matching index entry for '{}' in {} (fields={}) found".format(
                    instance, self.get_doc_type(), fields
                )
            )
            return True

        for name, field in self.get_fields().items():
            if fields is not None and name not in fields:
                logger.debug("Skipping field '{}'...".format(name))
                continue

            index_value = index_entry.get(name)
            instance_value = field.get_from_instance(instance)

            if not isinstance(index_value, type(instance_value)):
                logger.debug(
                    "Ignoring non-matching types {}, {}".format(
                        type(index_value), type(instance_value)
                    )
                )
            elif hasattr(field, "model") and hasattr(field.model, "_search_meta"):
                if isinstance(instance_value, dict) and instance_value:
                    _queryset = field.model._search_meta().get_base_qs()
                    _maybe_instance = _queryset.filter(pk=instance_value.get("pk"))
                    if (
                            _maybe_instance.exists() and
                            field.model._search_meta().has_index_changed(
                                _maybe_instance.get(),
                                fields=field.get_fields().keys()
                            )
                    ):
                        return True
                elif isinstance(instance_value, list) and instance_value:
                    for _el in instance_value:
                        _queryset = field.model._search_meta().get_base_qs()
                        _maybe_instance = _queryset.filter(pk=_el.get("pk"))
                        if (
                                _maybe_instance.exists() and
                                field.model._search_meta().has_index_changed(
                                    _maybe_instance.get(),
                                    fields=field.get_fields().keys()
                                )
                        ):
                            return True
            elif index_value != instance_value:
                sep_length = min(80, 2 + len(str(index_value)))
                logger.debug(
                    "Found mismatched index element '{}':\n {}\n {}\n {}".format(
                        name,
                        pprint.pformat(index_value),
                        "".join(["^" for i in range(sep_length)]),
                        pprint.pformat(instance_value)
                    )
                )
                return True

        logger.debug(
            "Index entry for '{}' in {} (fields={}) has not changed".format(
                instance, self.get_doc_type(), fields
            )
        )
        return False

    def should_index(self, instance):
        try:
            return self.has_index_changed(instance)
        except Exception as exc:
            import traceback; traceback.print_exc()
            logger.error(
                "Exception during 'should_index': {}".format(str(exc))
            )

    def should_dispatch_dependencies(self, instance):
        if not self.dispatch_dependencies:
            return False

        try:
            return self.has_index_changed(instance)
        except Exception as exc:
            import traceback; traceback.print_exc()
            logger.error(
                "Exception during 'should_dispatch_dependencies': {}".format(str(exc))
            )

    def get_dependencies(self):
        dependencies = self.dependencies.copy()
        for model, query in self.dependencies.items():
            if isinstance(model, str):
                (app_name, model_name) = model.split('.')
                model_cls = apps.get_model(app_name, model_name)
                dependencies.pop(model)
                dependencies[model_cls] = query

        return dependencies

    def should_index_for_dependency(self, instance, queryset):
        return queryset.exists()

    def get_search(self):
        s = dsl.Search(using=self.client)
        s = s.index(self.get_index())
        return s.doc_type(TypeAwareSerializableHit.make_callback(self))

    def create_index(self):
        """
        Creates an index and removes any previously-installed index mapping.
        """
        index = self.get_index()
        es = get_client(self.connection)

        if self.client.indices.exists(index=index):
            logger.debug("Deleting index '{}'".format(index))
            self.client.indices.delete(index=index)

        logger.debug("Creating index '{}'".format(index))
        self.client.indices.create(index=index)

    def configure_index(self):
        """
        Handles configuration of index settings.

        Elasticsearch requires that 'number_of_replicas' be set while an index is opened.
        All other configuration is set after index is closed.
        """
        settings = self.get_settings()
        index = self.get_index()

        config = self.get_index_settings()
        index_settings = config.pop('index', {})
        if index_settings and index_settings.get('number_of_replicas', None) is not None:
            log_msg = "Setting number_of_replicas={} on '{}'"
            logger.debug(log_msg.format(index_settings.get('number_of_replicas'), index))
            replica_settings = {
                'index': {
                    'number_of_replicas': index_settings.pop('number_of_replicas')
                }
            }
            self.client.indices.open(index=index)
            self.client.indices.put_settings(settings=replica_settings, index=index)

            if len(index_settings):
                config.update(index_settings)
            if len(config):
                settings = merge([config, settings])

        try:
            self.client.indices.close(index=index)
            logger.debug("Updating settings for index '{}': {}".format(index, settings))
            self.client.indices.put_settings(settings=settings, index=index)
        except exceptions.RequestError as e:
            if settings:
                raise e
            logger.debug("No settings to update for index '{}'".format(index))
        finally:
            self.client.indices.open(index=index)

    def check_mapping(self):
        mapping = self.get_mapping()
        index = self.get_index()

        if not self.client.indices.exists(index=index):
            return False

        def validate_properties(lhs, rhs):
            if len(lhs) != len(rhs):
                logger.warning(
                    "Size of properties differs: {}, {}".format(len(lhs), len(rhs))
                )
                return False

            for name, info in lhs.items():
                if name not in rhs:
                    return False

                # the default mapping_type is 'object' and is not explicitly
                # given as the 'type' parameter of 'properties'.
                if info.get('type', 'object') != rhs[name].get('type', 'object'):
                    return False
                if 'properties' in info:
                    if not validate_properties(
                        info['properties'],
                        rhs[name]['properties']
                    ):
                        return False

            return True

        active_mapping = self.client.indices.get_mapping(index=index)
        document = active_mapping.get(index).get('mappings')
        return validate_properties(
            mapping.get('properties'), document.get('properties')
        )

    def put_mapping(self):
        """
        Initializes a (possibly new) index and installs the given mapping.
        """
        self.create_index()
        self.configure_index()

        mapping = self.get_mapping()
        index = self.get_index()

        log_msg = "Updating mapping for index '{}': {}"
        logger.debug(log_msg.format(index, mapping))
        self.client.indices.put_mapping(**mapping, index=index)

    def get_base_qs(self):
        # Some objects have a default ordering, which only slows
        # things down here.
        return self.model.objects.order_by()

    def get_qs(self, since=None, until=None, limit=None):
        qs = self.get_base_qs()
        filters = {}

        if since:
            filters["{}__gte".format(self.date_field)] = since
        if until:
            filters["{}__lte".format(self.date_field)] = until

        qs = qs.filter(**filters)

        # TODO: is this change acceptable?
        if self.index_ordering is not None:
            qs = qs.order_by(*self.index_ordering)

        if limit:
            qs = qs[:limit]

        return qs

    def get_entry_mapping(self, instance):
        """
        Fetches mapping which represents this instance in the index.
        """
        try:
            logger.debug("Getting entry mapping for instance '{}'".format(instance))
            query = self.get_search().query("match", pk=instance.pk)
            hits = query.execute().hits
            if not len(hits):
                logger.debug("No entries found.".format(instance))
                return None
            if len(hits) > 1:
                logger.debug("Multiple entries found: {}".format(hits))
                return None
            return hits[0].to_dict(recursive=True)
        except exceptions.ConnectionTimeout as exc:
            msg = "Index entry request for '{}' timed out."
            logger.warning(msg.format(instance))
        except exceptions.ConnectionError as exc:
            msg = "Index entry request for '{}' encountered a connection error."
            logger.warning(msg.format(instance))

    def index_instance(self, instance):
        if self.get_qs().filter(pk=instance.pk).exists():
            try:
                logger.debug("Indexing instance '{}'".format(instance))
                self.client.index(
                    index=self.get_index(),
                    id=instance.pk,
                    body=self.prepare(instance),
                    params={'refresh': 'true'}
                )
            except exceptions.ConnectionTimeout as exc:
                msg = "Index request for '{}' timed out."
                logger.warning(msg.format(instance))
            except exceptions.ConnectionError as exc:
                msg = "Index request for '{}' encountered a connection error."
                logger.warning(msg.format(instance))
        else:
            try:
                instance_repr = '{} ({})'.format(instance.__class__.__name__, instance.pk)
                logger.debug("Un-indexing instance {}".format(instance_repr))
                self.client.delete(
                    index=self.get_index(),
                    id=instance.pk,
                    ignore=404,
                    params={'refresh': 'true'}
                )
            except exceptions.ConnectionTimeout as exc:
                msg = "Unindex request for '{}' timed out."
                logger.warning(msg.format(instance))
            except exceptions.ConnectionError as exc:
                msg = "Unindex request for '{}' encountered a connection error."
                logger.warning(msg.format(instance))

    def set_index_refresh(self, index, state):
        index_settings = {'index': {'refresh_interval': None if state else "-1"}}
        self.client.indices.put_settings(settings=index_settings, index=index)
        if not state:
            self.client.indices.forcemerge(index=index)

    def get_chunksize(self, queryset):
        chunk_factor = getattr(settings, 'ELASTICSEARCH_INDEX_CHUNK_FACTOR', 20)
        return CHUNKSIZE * max(1, int(queryset.count() / (CHUNKSIZE * chunk_factor)))

    def bulk_index(self, qs):
        index = self.get_index()

        if not qs.exists():
            logger.info("Bulk index request received for empty queryset. Skipping.")
            return None

        try:
            assert qs.count() > CHUNKSIZE, "Falling back to non-chunked indexing."

            chunksize = self.get_chunksize(qs)
            logger.info("Using chunk size of '{}'".format(chunksize))

            responses = []
            for chunk in queryset_iterator(qs, chunksize=chunksize):
                try:
                    actions = [
                        {'_index': index,
                         '_id': instance.pk,
                         '_source': self.prepare(instance)}
                        for instance in chunk.iterator()
                    ]
                    responses.append(
                        bulk(
                            client=self.client,
                            actions=tuple(actions),
                            params={'refresh': 'true'}
                        )
                    )
                except BulkIndexError as e:
                    logger.error("Failure during bulk index: {}".format(e))
                except exceptions.ConnectionTimeout as exc:
                    logger.warning("Bulk index request timed out.")
                except exceptions.ConnectionError as exc:
                    logger.warning("Bulk index request encountered a connection error.")

            return responses

        except AssertionError:
            try:
                actions = [
                    {'_index': index,
                     '_id': instance.pk,
                     '_source': self.prepare(instance)}
                    for instance in qs.iterator()
                ]
                return bulk(
                    client=self.client,
                    actions=tuple(actions),
                    params={'refresh': 'true'}
                )
            except BulkIndexError as e:
                logger.error("Failure during bulk index: {}".format(e))
            except exceptions.ConnectionTimeout as exc:
                logger.warning("Bulk index request timed out.")
            except exceptions.ConnectionError as exc:
                logger.warning("Bulk index request encountered a connection error.")

    def bulk_clear(self):
        index = self.get_index()

        try:
            actions = [
                {'_index': index, '_op_type' : 'delete', '_id': hit.pk}
                for hit in self.get_search()
            ]
            log_msg = "Removing all {} instances from {})."
            logger.debug(log_msg.format(len(actions), index))
            return bulk(
                client=self.client,
                actions=tuple(actions),
                ignore=404,
                params={'refresh': 'true'}
            )
        except BulkIndexError as e:
            logger.error("Failure during bulk clear: {}".format(e))
        except exceptions.ConnectionTimeout as exc:
            msg = "Bulk clear request timed out."
            logger.warning(msg.format(instance))
        except exceptions.ConnectionError as exc:
            msg = "Bulk clear request encountered a connection error."
            logger.warning(msg.format(instance))

    def bulk_prune(self):
        index = self.get_index()

        pruned = self.model.objects.difference(self.get_qs())
        qs = self.model.objects.filter(pk__in=pruned.values_list('pk', flat=True))

        if not qs.exists():
            logger.info("Bulk prune request has no objects to remove. Skipping.")
            return None

        try:
            assert qs.count() > CHUNKSIZE, "Falling back to non-chunked indexing."

            chunksize = self.get_chunksize(qs)
            logger.info("Using chunk size of '{}'".format(chunksize))

            responses = []
            for chunk in queryset_iterator(qs, chunksize=chunksize):
                try:
                    actions = [
                        {'_index': index,
                         '_op_type' : 'delete',
                         '_id': instance.pk}
                        for instance in chunk.iterator()
                    ]
                    responses.append(
                        bulk(
                            client=self.client,
                            actions=tuple(actions),
                            ignore=404,
                            params={'refresh': 'true'}
                        )
                    )
                except BulkIndexError as e:
                    logger.warning("Failure during bulk prune: {}".format(e))
                except exceptions.ConnectionTimeout as exc:
                    msg = "Bulk prune request timed out."
                    logger.warning(msg.format(instance))
                except exceptions.ConnectionError as exc:
                    msg = "Bulk prune request encountered a connection error."
                    logger.warning(msg.format(instance))

            return responses
        except AssertionError:
            try:
                actions = [
                    {'_index': index,
                     '_id': instance.pk,
                     '_source': self.prepare(instance)}
                    for instance in qs.iterator()
                ]
                return bulk(
                    client=self.client,
                    actions=tuple(actions),
                    ignore=404,
                    params={'refresh': 'true'}
                )
            except BulkIndexError as e:
                logger.warning("Failure during bulk prune: {}".format(e))
            except exceptions.ConnectionTimeout as exc:
                msg = "Bulk prune request timed out."
                logger.warning(msg.format(instance))
            except exceptions.ConnectionError as exc:
                msg = "Bulk prune request encountered a connection error."
                logger.warning(msg.format(instance))


class SearchDescriptor:
    def __get__(self, instance, type=None):
        if instance != None:
            msg = "Search isn't accessible via {} instances"
            raise AttributeError(msg.format(type.__name__))
        return type._search_meta().get_search()


class SearchMixin:
    @classmethod
    def _search_meta(cls):
        return getattr(cls, 'Search')(model=cls)

    def index(self):
        return self._search_meta().index_instance(self)

    search = SearchDescriptor()
