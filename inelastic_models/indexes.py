import threading
import logging
import gc

from elasticsearch.helpers import bulk, BulkIndexError
from elasticsearch import Elasticsearch
from elasticsearch import exceptions
import elasticsearch_dsl as dsl

from django.conf import settings
from django.apps import apps
from django.db import models

from .fields import FieldMappingMixin, KitchenSinkField
from .utils import merge

logger = logging.getLogger(__name__)

CHUNKSIZE = 1000
_cache = threading.local()


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


class AwareResult(dsl.response.Hit):
    def __init__(self, document, search_meta):
        super().__init__(document)

        for name, field in search_meta.get_fields().items():
            self[name] = field.to_python(self[name])

    @classmethod
    def make_callback(cls, search_meta):
        def callback(document):
            return cls(document, search_meta)
        return callback


class Search(FieldMappingMixin):
    connection = 'default'
    mapping = None
    index_by = CHUNKSIZE
    date_field = 'modified_on'

    @classmethod
    def bind_to_model(cls, model):
        setattr(model, 'Search', cls)

    # A dictionary whose keys are other models that this model's index
    # depends on, and whose values are query set paramaters for this model
    # to select the instances that depend on an instance of the key model.
    # For example, the index for BlogPost might use information from Author,
    # so it would have dependencies = {Author: 'author'}.
    # When an Author is saved, this causes BlogPost's returned by the query
    # BlogPost.objects.filter(author=instance) to be re-indexed.
    dependencies = {}

    def get_settings(self):
        field_settings = super().get_settings()
        if getattr(settings, 'ELASTICSEARCH_KITCHEN_SINK_FIELD', False):
            field_settings = merge([field_settings,
                                    KitchenSinkField().get_field_settings()])
        return field_settings

    def get_mapping(self):
        mapping = super().get_mapping()
        if getattr(settings, 'ELASTICSEARCH_KITCHEN_SINK_FIELD', False):
            mapping['properties']['kitchen_sink'] = KitchenSinkField().get_field_mapping()
        return mapping

    def get_index(self):
        index_name = settings.ELASTICSEARCH_CONNECTIONS[self.connection]['INDEX_NAME']
        return '{}--{}'.format(index_name, self.get_doc_type())

    def get_doc_type(self):
        return "{}_{}".format(self.model._meta.app_label, self.model._meta.model_name)

    def get_dependencies(self):
        dependencies = self.dependencies.copy()
        for model, query in self.dependencies.items():
            if isinstance(model, str):
                (app_name, model_name) = model.split('.')
                model_cls = apps.get_model(app_name, model_name)
                dependencies.pop(model)
                dependencies[model_cls] = query
        return dependencies

    def get_es(self):
        es_client = getattr(_cache, 'es_client', None)
        if es_client is None:
            config = settings.ELASTICSEARCH_CONNECTIONS[self.connection]
            (host_list, options) = (config.get('HOSTS', []),
                                    config.get('CONNECTION_OPTIONS', {}))
            es_client = Elasticsearch(hosts=host_list, **options)
            setattr(_cache, 'es_client', es_client)

        return es_client

    def get_search(self):
        s = dsl.Search(using=self.get_es())
        s = s.index(self.get_index())
        return s.doc_type(**{'_doc': AwareResult.make_callback(self)})

    def create_index(self):
        """
        Creates an index and removes any previously-installed index mapping.
        """
        index = self.get_index()
        es = self.get_es()

        if es.indices.exists(index):
            logger.warning("Deleting index '{}'".format(index))
            es.indices.delete(index)

        logger.debug("Creating index '{}'".format(index))
        es.indices.create(index)
        es.indices.refresh(index=index)
        es.cluster.health(wait_for_status='yellow')

    def configure_index(self):
        """
        Handles configuration of index settings.

        Elasticsearch requires that 'number_of_replicas' be set while an index is opened.
        All other configuration is set after index is closed.
        """
        settings = self.get_settings()
        index = self.get_index()
        es = self.get_es()

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
            es.indices.open(index)
            es.indices.put_settings(replica_settings, index=index)
            es.indices.refresh(index=index)

            if len(index_settings):
                config.update(index_settings)
            if len(config):
                settings = merge([config, settings])

        try:
            es.indices.close(index)
            logger.debug("Updating settings for index '{}': {}".format(index, settings))
            es.indices.put_settings(settings, index=index)
        except exceptions.RequestError as e:
            if settings:
                raise e
            logger.debug("No settings to update for index '{}'".format(index))
        finally:
            es.indices.open(index)
            es.indices.refresh(index=index)

    def check_mapping(self):
        mapping = self.get_mapping()
        index = self.get_index()
        es = self.get_es()

        if not es.indices.exists(index=index):
            return False

        def validate_properties(lhs, rhs):
            for name, info in lhs.items():
                if name not in rhs:
                    return False
                if info['type'] != rhs[name]['type']:
                    return False
                if 'properties' in info:
                    validate_properties(info['properties'],
                                        rhs[name]['properties'])
            return True

        active_mapping = es.indices.get_mapping(index=index)
        document = active_mapping.get(index).get('mappings')
        return validate_properties(mapping.get('properties'),
                                   document.get('properties'))

    def put_mapping(self):
        """
        Initializes a (possibly new) index and installs the given mapping.
        """
        self.create_index()
        self.configure_index()

        mapping = self.get_mapping()
        index = self.get_index()
        es = self.get_es()

        log_msg = "Updating mapping for index '{}': {}"
        logger.debug(log_msg.format(index, mapping))
        es.indices.put_mapping(mapping,
                               index=index)

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

        if limit:
            qs = qs[:limit]

        return qs

    def index_instance(self, instance):
        if self.get_qs().filter(pk=instance.pk).exists():
            logger.debug("Indexing instance '{}'".format(instance))
            self.get_es().index(
                index=self.get_index(),
                id=instance.pk,
                body=self.prepare(instance))
        else:
            try:
                instance.refresh_from_db()
                logger.debug("Un-indexing instance '{}'".format(instance))
            except:
                logger.debug("Un-indexing instance '{}'".format(instance.pk))
            finally:
                self.get_es().delete(
                    index=self.get_index(),
                    id=instance.pk,
                    ignore=404)

    def index_qs(self, qs):
        index = self.get_index()
        es = self.get_es()

        try:
            assert qs.count() > self.index_by, "Falling back to non-chunked indexing."

            responses = []
            for chunk in queryset_iterator(qs, chunksize=self.index_by):
                try:
                    actions = [
                        {'_index': index,
                         '_id': instance.pk,
                         '_source': self.prepare(instance)}
                        for instance in chunk.iterator()
                    ]
                    responses.append(bulk(client=es, actions=tuple(actions)))
                    es.indices.refresh(index=index)
                except BulkIndexError as e:
                    logger.error("Failure during bulk index: {}".format(e))
            return responses
        except AssertionError:
            if not qs.count():
                logger.info("No objects to index")
                return None

            try:
                actions = [
                    {'_index': index,
                     '_id': instance.pk,
                     '_source': self.prepare(instance)}
                    for instance in qs.iterator()
                ]
                response = bulk(client=es, actions=tuple(actions))
                es.indices.refresh(index=index)
                return response
            except BulkIndexError as e:
                logger.error("Failure during bulk index: {}".format(e))

    def bulk_clear(self):
        index = self.get_index()
        es = self.get_es()

        try:
            actions = [{'_index': index,
                        '_op_type' : 'delete',
                        '_id': hit.pk}
                       for hit in self.get_search()]
            log_msg = "Removing all {} instances from {})."
            logger.info(log_msg.format(len(actions), index))
            return bulk(client=es, actions=tuple(actions))
        except BulkIndexError as e:
            logger.error("Failure during bulk clear: {}".format(e))

    def bulk_prune(self):
        index = self.get_index()
        es = self.get_es()

        pruned = self.model.objects.difference(self.get_qs())
        qs = self.model.objects.filter(pk__in=pruned.values_list('pk', flat=True))

        try:
            assert qs.count() > self.index_by, "Falling back to non-chunked indexing."

            responses = []
            for chunk in queryset_iterator(qs, chunksize=self.index_by):
                try:
                    actions = [
                        {'_index': index,
                         '_op_type' : 'delete',
                         '_id': instance.pk}
                        for instance in chunk.iterator()
                    ]
                    logger.info("Pruning {} {} instances.".format(qs.count(), self.model.__name__))
                    responses.append(bulk(client=es, actions=tuple(actions)))
                except BulkIndexError as e:
                    logger.warning("Failure during bulk prune: {}".format(e))
            return responses
        except AssertionError:
            if not qs.count():
                logger.info("No objects to prune")
                return None

            try:
                actions = [
                    {'_index': index,
                     '_id': instance.pk,
                     '_source': self.prepare(instance)}
                    for instance in qs.iterator()
                ]
                logger.info("Pruning {} {} instances.".format(qs.count(), self.model.__name__))
                return bulk(client=es, actions=tuple(actions))
            except BulkIndexError as e:
                logger.warning("Failure during bulk prune: {}".format(e))


class SearchDescriptor(object):
    def __get__(self, instance, type=None):
        if instance != None:
            msg = "Search isn't accessible via {} instances"
            raise AttributeError(msg.format(type.__name__))
        return type._search_meta().get_search()


class SearchMixin(object):
    @classmethod
    def _search_meta(cls):
        return getattr(cls, 'Search')(model=cls)

    def index(self):
        return self._search_meta().index_instance(self)

    search = SearchDescriptor()
