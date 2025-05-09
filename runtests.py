import sys
import os

from django.conf import settings
from django import VERSION

ELASTICSEARCH_HOST = os.environ.get('ELASTICSEARCH_HOST', 'http://elasticsearch:9200')


settings.configure(
    DEBUG=False,
    DATABASES={
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
        }
    },
    INSTALLED_APPS=(
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',

        'inelastic_models',
    ),
    MIGRATION_MODULES={
        'inelastic_models': 'inelastic_models.test_migrations'
    },
    MIDDLEWARE_CLASSES=[],
    ELASTICSEARCH_CONNECTIONS={
        'default': {
            'HOSTS': [ELASTICSEARCH_HOST],
            'INDEX_NAME': 'inelastic_models',
            'INDEX_OPTIONS': {
                'max_ngram_diff': 2
            }
        }
    },
    TEMPLATES=[{
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'OPTIONS': {
            'context_processors': ['django.contrib.auth.context_processors.auth'],
            'loaders': [
                ('django.template.loaders.locmem.Loader', {
                    'test_index_template_name.txt': 'Template_{{ object.name }}',
                }),
            ],
        },
    }],
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "simple": {"format": "%(asctime)s %(levelname)s [%(name)s] %(message)s"}
        },
        "filters": {},
        "handlers": {
            "console": {
                "level": "DEBUG",
                "class": "logging.StreamHandler",
                "formatter": "simple",
            },
        },
        "root": {
            "handlers": ["console"],
            "propagate": False,
            "level": "WARN",
        }
    }
)

from django import setup
setup()


from inelastic_models.tests import SearchTestRunner
test_runner = SearchTestRunner(verbosity=1)
failures = test_runner.run_tests(['inelastic_models.tests'])
if failures:
    sys.exit(failures)
