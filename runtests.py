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
    }]
)

if VERSION[:2] >= (1, 7):
    from django import setup
else:
    setup = lambda: None

setup()


from inelastic_models.tests import SearchTestRunner
test_runner = SearchTestRunner(verbosity=1)
failures = test_runner.run_tests(['inelastic_models.tests'])
if failures:
    sys.exit(failures)
