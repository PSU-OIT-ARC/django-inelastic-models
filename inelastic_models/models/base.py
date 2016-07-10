from __future__ import unicode_literals
from __future__ import absolute_import

from itertools import chain
import threading
import dateutil
import logging
import six

from elasticsearch.helpers import bulk, BulkIndexError
from elasticsearch import Elasticsearch
from elasticsearch import exceptions
import elasticsearch_dsl as dsl

from django.utils.functional import cached_property
from django.template.loader import render_to_string
from django.core.exceptions import FieldDoesNotExist
from django.db.models.fields.related import ForeignObjectRel
from django.db import models
from django.conf import settings
from django.apps import apps

_cache = threading.local()
logger = logging.getLogger(__name__)


def merge(items, overwrite=True):
    if not items:
        return {}

    if len(items) == 1:
        return items[0]

    if all(isinstance(i, dict) for i in items):
        # Merge dictionaries by recursively merging each key.
        keys = set(chain.from_iterable(six.iterkeys(i) for i in items))
        return dict((k, merge([i[k] for i in items if k in i], overwrite)) for k in keys)
    elif all(isinstance(i, list) for i in items):
        # Merge lists by chaining them together.
        return list(chain.from_iterable(items))
    elif all(isinstance(i, set) for i in items):
        # Merge sets by unioning them together.
        return set().union(*items)
    else:
        if overwrite:
            # Merge other values by selecting the last one.
            return items[-1]
        raise ValueError("Collision while merging. Values: %s" % items)

class SearchField(object):
    mapping = None
    mapping_type = 'string'
    index = None #Set to 'analyzed' 'not_analyzed' or 'no'

    def __init__(self, *args, **kwargs):
        if 'index' in kwargs:
            self.index = kwargs.pop('index')

        super(SearchField, self).__init__(*args, **kwargs)

    def get_field_mapping(self):
        if self.mapping is not None:
            return self.mapping

        mapping = {'type': self.mapping_type}
        if self.index is not None:
            mapping['index'] = self.index

        return mapping

    def get_field_settings(self):
        return {}

    def get_from_instance(self, instance):
        return None

class TemplateField(SearchField):
    def __init__(self, template_name):
        self.template_name = template_name
        super(TemplateField, self).__init__(*args, **kwargs)

    def get_from_instance(self, instance):
        context = {'object': self.instance}
        return render_to_string(template_name, context)

class EmailURLAllField(SearchField):
    def get_field_settings(self):
        settings = super(EmailURLAllField, self).get_field_settings()
        settings = merge([settings, {
            'analysis': {
                'analyzer': {
                    'email_url_analyzer': {
                        'tokenizer': 'email_url_tokenizer',
                        'filter': ['lowercase'],
                    }
                },
                'tokenizer': {
                    'email_url_tokenizer' : {
                        'type': 'uax_url_email',
                    }
                },
            }
        }])

        return settings

    def get_field_mapping(self):
        mapping = super(EmailURLAllField, self).get_field_mapping()
        mapping['analyzer'] = 'email_url_analyzer'
        return mapping

class AttributeField(SearchField):
    def __init__(self, attr, *args, **kwargs):
        self.path = attr.split(".")
        super(AttributeField, self).__init__(*args, **kwargs)

    def get_from_instance(self, instance):
        for attr in self.path:
            if instance is None:
                return None

            try:
                options = instance._meta
                instance = getattr(instance, attr)
            except AttributeError as exc:
                msg = "'{0}' not defined on {1}: {2!s}"
                logger.warning(msg.format(self.path, instance, e))

        return instance

    def to_python(self, value):
        return value

class StringField(AttributeField):
    def get_from_instance(self, instance):
        value = super(StringField, self).get_from_instance(instance)
        if value is not None and callable(value):
            value = value()
        return six.text_type(value) or ""

class NGramField(StringField):
    min_gram = 2
    max_gram = 4

    def __init__(self, *args, **kwargs):
        if 'min_gram' in kwargs:
            self.min_gram = kwargs.pop('min_gram')

        if 'max_gram' in kwargs:
            self.max_gram = kwargs.pop('max_gram')

        super(NGramField, self).__init__(*args, **kwargs)

    def get_analyzer_name(self):
        return "ngram_analyzer_%d_%d" % (self.min_gram, self.max_gram)

    def get_field_mapping(self):
        mapping = super(NGramField, self).get_field_mapping()
        mapping['analyzer'] = self.get_analyzer_name()
        return mapping

    def get_field_settings(self):
        settings = super(NGramField, self).get_field_settings()
        analyzer_name = self.get_analyzer_name()
        tokenizer_name = "ngram_tokenizer_%d_%d" % (self.min_gram, self.max_gram)

        settings = merge([settings, {
            'analysis': {
                'analyzer': {
                    analyzer_name: {
                        'tokenizer': tokenizer_name,
                        'filter': ['lowercase'],
                    }
                },
                'tokenizer': {
                    tokenizer_name : {
                        'type': 'nGram',
                        'min_gram': self.min_gram,
                        'max_gram': self.max_gram,
                        'token_chars': [ "letter", "digit" ]
                    }
                },
            }
        }])

        return settings

class MultiField(AttributeField):
    def get_from_instance(self, instance):
        manager = super(MultiField, self).get_from_instance(instance)
        return self.render(manager)

    def render(self, manager):
        return "\n".join(six.text_type(i) for i in manager.all())

class ListField(MultiField):
    def render(self, manager):
        return list(six.text_type(i) for i in manager.all())

class IntegerField(AttributeField):
    mapping_type = 'integer'

class BooleanField(AttributeField):
    mapping_type = 'boolean'

class DateField(AttributeField):
    mapping_type = 'date'

    def to_python(self, value):
        if isinstance(value, six.text_type):
            return dateutil.parser.parse(value).date()
        return value

class SearchDescriptor(object):
    def __get__(self, instance, type=None):
        if instance != None:
            raise AttributeError("Search isn't accessible via %s instances" % type.__name__)
        return type._search_meta().get_search()

class FieldMappingMixin(object):
    attribute_fields = ()
    template_fields = ()
    other_fields = {}

    def __init__(self, *args, **kwargs):
        if 'model' in kwargs:
            self.model = kwargs.pop('model')

        if 'attribute_fields' in kwargs:
            self.attribute_fields = kwargs.pop('attribute_fields')

        if 'template_fields' in kwargs:
            self.template_fields = kwargs.pop('template_fields')

        if 'other_fields' in kwargs:
            self.other_fields = kwargs.pop('other_fields')

        super(FieldMappingMixin, self).__init__(*args, **kwargs)

    def get_attr_field(self, attr):
        # Figure out if the attribute is a model field, and if so, use it to
        # determine the search index field type.
        path = attr.split(".")
        name = path[-1]
        try:
            model = self.model
            for a in path[:-1]:
                model = model._meta.get_field(a).related_model
            field = model._meta.get_field(path[-1])

            if isinstance(field, models.BooleanField):
                return name, BooleanField(attr=attr)
            elif isinstance(field, models.IntegerField):
                return name, IntegerField(attr=attr)
            elif isinstance(field, models.DateField):
                return name, DateField(attr=attr)
            elif isinstance(field, models.EmailField):
                return name, StringField(attr=attr, index='not_analyzed')
            elif isinstance(field, models.ManyToManyField) or \
                 isinstance(field, ForeignObjectRel):
                return name, MultiField(attr=attr)
            else:
                return name, StringField(attr=attr)

        except models.FieldDoesNotExist:
            return name, StringField(attr=attr)
        except AttributeError as exc:
            if not hasattr(self, 'model'):
                return (name, StringField(attr=attr))
            raise exc

    def get_fields(self):
        fields = {}

        if hasattr(self, 'model'):
            fields['pk'] = IntegerField(attr="pk")

        for attr in self.attribute_fields:
            name, field = self.get_attr_field(attr)
            fields[name] = field

        for name in self.template_fields:
            fields[name] = TemplateField(
                template_name = "search/indexes/%s/%s_%s.html" % (
                    self.model._meta.app_label, self.model._meta.model_name, name))

        fields.update(self.other_fields)

        return fields

    def get_index_settings(self):
        connection_info = settings.ELASTICSEARCH_CONNECTIONS[self.connection]
        config = connection_info.get('OPTIONS', {})
        logger.debug("Using configuration: %s" % (config))

        if not config:
            return {'index': {}}
        return {'index': {
            'number_of_replicas': config.get('number_of_replicas', 1)}}

    def get_settings(self):
        return merge([f.get_field_settings() for f in self.get_fields().values()])

    def get_mapping(self):
        properties = dict((name, field.get_field_mapping())
                          for name, field in list(self.get_fields().items()))
        mapping = {'properties': properties}
        return mapping

    def prepare(self, instance):
        return dict((name, field.get_from_instance(instance))
                    for name, field in list(self.get_fields().items()))

class ObjectField(FieldMappingMixin, AttributeField):
    mapping_type = 'object'

    def get_field_mapping(self):
        mapping = super(ObjectField, self).get_field_mapping()
        mapping.update(self.get_mapping())
        return mapping

    def get_from_instance(self, instance):
        instance = super(ObjectField, self).get_from_instance(instance)
        return self.prepare(instance)

class MultiObjectField(FieldMappingMixin, MultiField):
    """ a list of dictionaries """
    mapping_type = 'nested'

    def get_field_mapping(self):
        mapping = super(MultiObjectField, self).get_field_mapping()
        mapping.update(self.get_mapping())
        return mapping

    def render(self, manager):
        object_list = []
        return [self.prepare(i) for i in manager.all()]

class AwareResult(dsl.result.Result):
    def __init__(self, document, search_meta):
        super(AwareResult, self).__init__(document)
        for name, field in search_meta.get_fields().items():
            self[name] = field.to_python(self[name])

    @classmethod
    def make_callback(cls, search_meta):
        def callback(document):
            return cls(document, search_meta)
        return callback

class Search(FieldMappingMixin):
    doc_type = None
    connection = 'default'
    mapping = None
    index_by = 1000
    date_field = 'modified_on'
    all_field = EmailURLAllField()

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
        settings = super(Search, self).get_settings()
        settings = merge([settings, self.all_field.get_field_settings()])
        return settings

    def get_mapping(self):
        mapping = super(Search, self).get_mapping()
        mapping['_all'] = self.all_field.get_field_mapping()
        return mapping

    def get_index(self):
        return '{}--{}'.format(
            settings.ELASTICSEARCH_CONNECTIONS[self.connection]['INDEX_NAME'],
            self.get_doc_type())

    def get_doc_type(self):
        if self.doc_type is not None:
            return self.doc_type
        else:
            return "%s_%s" % (self.model._meta.app_label, self.model._meta.model_name)

    def get_dependencies(self):
        dependencies = self.dependencies
        for model, query in dependencies.items():
            if isinstance(model, six.text_type):
                (app_name, model_name) = model.split('.')
                model_cls = apps.get_model(app_name, model_name)
                dependencies.pop(model)
                dependencies[model_cls] = query
        return dependencies

    def get_es(self):
        es_client = getattr(_cache, 'es_client', None)
        if es_client is None:
            host_list = settings.ELASTICSEARCH_CONNECTIONS[self.connection]['HOSTS']
            es_client = Elasticsearch(hosts=host_list)
            setattr(_cache, 'es_client', es_client)

        return es_client

    def get_search(self):
        s = dsl.Search(using=self.get_es())
        s = s.index(self.get_index())
        s = s.doc_type(**{self.get_doc_type(): AwareResult.make_callback(self)})
        return s

    def create_index(self):
        """
        Creates an index and removes any previously-installed index mapping.
        """
        doc_type = self.get_doc_type()
        index = self.get_index()
        es = self.get_es()

        if es.indices.exists(index):
            logger.warning("Deleting index '{}'".format(index))
            es.indices.delete(index)

        logger.debug("Creating index '%s'" % (index))
        es.indices.create(index)
        es.indices.refresh(index=index)
        es.cluster.health(wait_for_status='yellow')
        es.indices.flush(wait_if_ongoing=True)

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
            logger.debug("Setting number_of_replicas=%d on '%s'" % (
                index_settings.get('number_of_replicas'), index))
            replica_settings = {
                'index': {'number_of_replicas': index_settings.pop('number_of_replicas')}}
            es.indices.open(index)
            es.indices.put_settings(replica_settings, index)
            es.indices.refresh(index=index)
            es.indices.flush(wait_if_ongoing=True)

            if len(index_settings):
                config.update(index_settings)
            if len(config):
                settings = merge([config, settings])

        try:
            es.indices.close(index)
            logger.debug("Updating settings for index '%s': %s" % (index, settings))
            es.indices.put_settings(settings, index)
        except exceptions.RequestError as e:
            if settings:
                raise e
            logger.debug("No settings to update for index '%s'" % (index))
        finally:
            es.indices.open(index)
            es.indices.refresh(index=index)
            es.indices.flush(wait_if_ongoing=True)

    def put_mapping(self):
        """
        Initializes a (possibly new) index and installs the given mapping.
        """
        self.create_index()
        self.configure_index()

        doc_type = self.get_doc_type()
        mapping = self.get_mapping()
        index = self.get_index()
        es = self.get_es()

        logger.debug("Updating mapping for index '%s' and doc type '%s': %s" % (index, doc_type, mapping))
        es.indices.put_mapping(doc_type, mapping, index=index)

    def get_base_qs(self):
        # Some objects have a default ordering, which only slows
        # things down here.
        return self.model.objects.order_by()

    def get_qs(self, since=None, until=None, limit=None):
        qs = self.get_base_qs()
        filters = {}

        if since:
            filters["%s__gte" % self.date_field] = since
        if until:
            filters["%s__lte" % self.date_field] = until

        qs = qs.filter(**filters)

        if limit:
            qs = qs[:limit]

        return qs

    def index_instance(self, instance):
        if self.get_qs().filter(pk=instance.pk).exists():
            self.get_es().index(
                index=self.get_index(),
                doc_type=self.get_doc_type(),
                id=instance.pk,
                body=self.prepare(instance))
        else:
            logger.debug("Un-indexing instance (DB says it it not to be indexed).")
            self.get_es().delete(
                index=self.get_index(),
                doc_type=self.get_doc_type(),
                id=instance.pk,
                ignore=404)

    def index_qs(self, qs):
        doc_type = self.get_doc_type()
        index = self.get_index()
        es = self.get_es()

        actions = [{'_index': index,
                    '_type': doc_type,
                    '_id': instance.pk,
                    '_source': self.prepare(instance)}
                   for instance in qs.iterator()]

        try:
            response = bulk(client=es, actions=tuple(actions))
            es.indices.refresh(index=index)
            return response
        except BulkIndexError as e:
            print("Failure during bulk index: %s" % (six.text_type(e)))

    def bulk_clear(self):
        doc_type = self.get_doc_type()
        index = self.get_index()
        es = self.get_es()
        results = []

        try:
            actions = [{'_index': index,
                        '_type': doc_type,
                        '_op_type' : 'delete',
                        '_id': hit.pk}
                       for hit in self.get_search()]
            print("Removing all {} instances from {}).".format(
                len(actions), index))
            return bulk(client=es, actions=tuple(actions))
        except BulkIndexError as e:
            print("Failure during bulk clear: %s" % (six.text_type(e)))

    def bulk_prune(self):
        qs = self.model.objects.exclude(id__in=self.get_qs())
        doc_type = self.get_doc_type()
        index = self.get_index()
        es = self.get_es()

        actions = [{'_index': index,
                    '_type': doc_type,
                    '_op_type' : 'delete',
                    '_id': instance.pk }
                   for instance in qs.iterator()]

        try:
            print("Pruning %d %s instances." % (qs.count(), self.model.__name__))
            return bulk(client=es, actions=tuple(actions))
        except BulkIndexError as e:
            print("Failure during bulk prune: %s" % (six.text_type(e)))

class SearchMixin(object):
    @classmethod
    def _search_meta(cls):
        return getattr(cls, 'Search')(model=cls)

    def index(self):
        return self._search_meta().index_instance(self)

    search = SearchDescriptor()
