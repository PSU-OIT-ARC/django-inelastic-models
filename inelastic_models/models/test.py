from django.db import models

from ..indexes import SearchMixin, Search
from ..fields import (
    CharField,
    TextField,
    NGramField,
    CharListField,
    ObjectField,
    MultiObjectField,
)

TEST_MODEL_EXCLUDE_NAME = "NO"


class Model(SearchMixin, models.Model):
    name = models.CharField(max_length=256)
    email = models.EmailField(blank=True)
    date = models.DateField(null=True, blank=True)
    test_list = models.ForeignKey(
        "inelastic_models.SearchFieldModel",
        related_name="models",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    test_m2m = models.ManyToManyField("inelastic_models.SearchFieldModel", blank=True)
    modified_on = models.DateTimeField(auto_now=True)
    new_field = models.CharField(max_length=16, blank=True)

    @property
    def count_m2m(self):
        return str(self.test_m2m.count())

    def __str__(self):
        return self.name

    class Meta:
        app_label = "inelastic_models"


class ModelSearch(Search):
    attribute_fields = ["name", "date", "email", "count_m2m"]
    other_fields = {
        "text": TextField("name"),
        "ngram": NGramField("name"),
    }

    def get_base_qs(self):
        return self.model.objects.exclude(name=TEST_MODEL_EXCLUDE_NAME)


ModelSearch.bind_to_model(Model)


class SearchFieldModel(SearchMixin, models.Model):
    modified_on = models.DateTimeField(auto_now=True)
    related = models.ForeignKey(
        "inelastic_models.Model", on_delete=models.CASCADE, null=True, blank=True
    )

    def __str__(self):
        return "Related: {}".format(self.related)

    class Meta:
        app_label = "inelastic_models"


class SearchFieldModelSearch(Search):
    other_fields = {
        "model_list": CharListField("models"),
        "related": ObjectField(
            "related", model=Model, attribute_fields=["name", "modified_on"]
        ),
        "model_objects": MultiObjectField(
            "model_set",
            model=SearchFieldModel,
            attribute_fields=["name", "modified_on"],
        ),
    }

    dependencies = {
        "inelastic_models.Model": "related",
        "inelastic_models.Model": "models",
    }


SearchFieldModelSearch.bind_to_model(SearchFieldModel)
