import datetime
import logging
import copy

import dateutil

from django.template.loader import render_to_string
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db.models.fields.related import ForeignObjectRel
from django.db import models
from django.conf import settings

from .utils import merge

logger = logging.getLogger(__name__)


class SearchField:
    mapping_type = None
    index = True

    def get_analyzer(self):
        return (None, {})

    def get_tokenizer(self):
        return (None, {})

    def get_normalizer(self):
        return (None, {})

    def get_field_mapping(self):
        mapping = {'type': self.mapping_type}
        if self.index is False:
            mapping['index'] = False

        (a_name, _) = self.get_analyzer()
        if a_name is not None:
            mapping['analyzer'] = a_name

        (n_name, _) = self.get_normalizer()
        if n_name is not None:
            mapping['normalizer'] = n_name

        return mapping

    def get_field_settings(self):
        settings = {}

        (t_name, t_def) = self.get_tokenizer()
        if t_def:
            settings['tokenizer'] = dict([(t_name, t_def)])

        (a_name, a_def) = self.get_analyzer()
        if a_def:
            settings['analyzer'] = dict([(a_name, a_def)])

        (n_name, n_def) = self.get_normalizer()
        if n_def:
            settings['normalizer'] = dict([(n_name, n_def)])

        if not settings:
            return settings

        return {'analysis': settings}

    def get_from_instance(self, instance):
        return None


class TemplateField(SearchField):
    mapping_type = 'text'

    def __init__(self, template_name):
        super().__init__()

        self.template_name = template_name

    def get_from_instance(self, instance):
        context = {'object': instance}
        return render_to_string(template_name, context)


class KitchenSinkField(SearchField):
    """
    A field type to be used as a replacement for the deprecated '_all' field.
    """
    mapping_type = 'text'

    def get_field_settings(self):
        settings = super().get_field_settings()
        settings = merge([settings, {
            'analysis': {
                'analyzer': {
                    'kitchen_sink_analyzer': {
                        'tokenizer': 'kitchen_sink_tokenizer',
                        'filter': ['lowercase', ],
                    }
                },
                'tokenizer': {
                    'kitchen_sink_tokenizer' : {
                        'type': 'uax_url_email',
                    }
                },
            }
        }])

        return settings

    def get_field_mapping(self):
        mapping = super().get_field_mapping()
        mapping['analyzer'] = 'kitchen_sink_analyzer'
        return mapping


class AttributeField(SearchField):
    def __init__(self, attr):
        super().__init__()

        self.path = attr.split(".")

    def get_from_instance(self, instance):
        for attr in self.path:
            if instance is None:
                return None

            try:
                instance = getattr(instance, attr)
            except AttributeError as exc:
                msg = "'{0}' not defined on {1}: {2!s}"
                logger.warning(msg.format(self.path, instance, exc))
                return None
            except ObjectDoesNotExist as exc:
                msg = "Reference '{}' on '{}' does not exist."
                logger.warning(msg.format(attr, instance))
                return None

        return instance

    def to_python(self, value):
        return value


class StringField(AttributeField):
    def get_from_instance(self, instance):
        value = super().get_from_instance(instance)
        if value is not None and callable(value):
            value = value()
        return str(value) or ""


class KeywordField(StringField):
    mapping_type = 'keyword'

    def get_normalizer(self):
        return (
            'keyword_normalizer', {
                'filter': ['trim', 'lowercase']
            }
        )


class CharField(StringField):
    mapping_type = 'text'

    def get_analyzer(self):
        return (
            'keyword_analyzer', {
                'tokenizer': 'keyword',
                'filter': ['trim', 'lowercase']
            }
        )


class TranslationField(CharField):
    def __init__(self, attr, *args, **kwargs):
        self.language_name = kwargs.pop('language', None)
        super().__init__(attr, *args, **kwargs)

    def get_field_mapping(self):
        mapping = super().get_field_mapping()
        if self.language_name is not None:
            mapping['analyzer'] = self.language_name
        return mapping


class TextField(StringField):
    mapping_type = 'text'


class NGramField(StringField):
    mapping_type = 'text'
    min_gram = 2
    max_gram = 4

    def __init__(self, *args, **kwargs):
        if 'min_gram' in kwargs:
            self.min_gram = kwargs.pop('min_gram')
        if 'max_gram' in kwargs:
            self.max_gram = kwargs.pop('max_gram')

        super().__init__(*args, **kwargs)

    def get_tokenizer(self):
        name = "ngram_tokenizer_{}_{}".format(self.min_gram, self.max_gram)
        return (name, {'type': 'ngram',
                       'min_gram': self.min_gram,
                       'max_gram': self.max_gram,
                       'token_chars': ["letter", "digit"]})

    def get_analyzer(self):
        (t_name, _) = self.get_tokenizer()
        name = "ngram_analyzer_{}_{}".format(self.min_gram, self.max_gram)
        return (name, {'tokenizer': t_name, 'filter': ['lowercase']})


class IntegerField(AttributeField):
    mapping_type = 'integer'


class FloatField(AttributeField):
    mapping_type = 'float'


class DecimalField(AttributeField):
    mapping_type = 'double'


class BooleanField(AttributeField):
    mapping_type = 'boolean'


class DateField(AttributeField):
    mapping_type = 'date'

    def to_python(self, value):
        if isinstance(value, str):
            return dateutil.parser.parse(value).date()

        return super().to_python(value)


class DurationField(AttributeField):
    mapping_type = 'unsigned_long'

    def to_python(self, value):
        return value.total_seconds


class ListField(AttributeField):
    def get_from_instance(self, instance):
        instance = super().get_from_instance(instance)
        if instance is None:
            return {}

        if hasattr(instance, 'all'):
            instance = instance.all()
        return list(str(i) for i in instance)


class KeywordListField(ListField):
    mapping_type = 'keyword'


class TextListField(ListField):
    mapping_type = 'text'


class MultiField(AttributeField):
    mapping_type = 'text'


class RenderedAttributeField(AttributeField):
    mapping_type = 'text'

    def get_from_instance(self, instance):
        reference = super().get_from_instance(instance)
        return self.render(reference)

    def render(self, manager):
        raise NotImplementedError


class FieldMappingMixin(object):
    attribute_fields = ()
    template_fields = ()
    other_fields = {}

    use_all_field = getattr(settings, 'ELASTICSEARCH_USE_ALL_FIELD', False)
    all_field_name = getattr(settings, 'ELASTICSEARCH_ALL_FIELD_NAME', '_all')
    index_ordering = getattr(settings, 'ELASTICSEARCH_INDEX_ORDERING', None)

    def __init__(self, *args, **kwargs):
        if 'model' in kwargs:
            self.model = kwargs.pop('model')
        if 'attribute_fields' in kwargs:
            self.attribute_fields = kwargs.pop('attribute_fields')
        if 'template_fields' in kwargs:
            self.template_fields = kwargs.pop('template_fields')
        if 'other_fields' in kwargs:
            self.other_fields = kwargs.pop('other_fields')

        super().__init__(*args, **kwargs)

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
                return (name, BooleanField(attr=attr))
            elif isinstance(field, (models.ForeignKey,
                                    models.IntegerField)):
                return (name, IntegerField(attr=attr))
            elif isinstance(field, models.FloatField):
                return (name, FloatField(attr=attr))
            elif isinstance(field, models.DecimalField):
                return (name, DecimalField(attr=attr))
            elif isinstance(field, models.DateField):
                return (name, DateField(attr=attr))
            elif isinstance(field, models.DurationField):
                return (name, DurationField(attr=attr))
            elif isinstance(field, models.CharField):
                return (name, CharField(attr=attr))
            elif isinstance(field, models.TextField):
                return (name, TextField(attr=attr))
            else:
                return (name, KeywordField(attr=attr))

        except models.FieldDoesNotExist:
            return (name, KeywordField(attr=attr))
        except AttributeError as exc:
            if not hasattr(self, 'model'):
                return (name, KeywordField(attr=attr))
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
        options = copy.deepcopy(connection_info.get('INDEX_OPTIONS', {}))

        if options.get('number_of_replicas', None) is None:
            options.update({'number_of_replicas': 1})

        logger.debug("Using index configuration: {}".format(options))
        return {'index': options}

    def get_settings(self):
        return merge([f.get_field_settings() for f in self.get_fields().values()])

    def get_mapping(self):
        properties = {}

        for name, field in self.get_fields().items():
            mapping = field.get_field_mapping()
            if all([self.use_all_field, 'properties' not in mapping]):
                mapping['copy_to'] = self.all_field_name
            properties[name] = mapping

        return {'properties': properties}

    def prepare(self, instance):
        return dict((name, field.get_from_instance(instance))
                    for name, field in list(self.get_fields().items()))


class ObjectFieldMixin(FieldMappingMixin):
    def get_field_mapping(self):
        mapping = super().get_field_mapping()
        mapping.update(self.get_mapping())
        return mapping

    def get_field_settings(self):
        settings = super().get_field_settings()
        settings = merge([settings, self.get_settings()])
        return settings

    
class ObjectField(ObjectFieldMixin, AttributeField):
    mapping_type = 'object'

    def get_from_instance(self, instance):
        instance = super().get_from_instance(instance)
        if instance is None:
            return {}

        return self.prepare(instance)


class MultiObjectField(ObjectFieldMixin, AttributeField):
    mapping_type = 'nested'

    def get_from_instance(self, instance):
        instance = super().get_from_instance(instance)
        if instance is None:
            return []

        if hasattr(instance, 'all'):
            instance = instance.all()
        return [self.prepare(i) for i in instance]
