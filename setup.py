import sys
from setuptools import find_packages, setup

setup(
    name='DjangoInelasticModels',
    version='1.5.0',
    author='Thom Linton',
    author_email='tlinton@pdx.edu',
    url='https://github.com/PSU-OIT-ARC/django-inelastic-models',
    long_description=open('README.rst').read(),

    packages=find_packages(),
    install_requires=['elasticsearch>=2.0.0,<5.0.0',
                      'elasticsearch-dsl>=2.0.0,<5.0.0',
                      'django>1.11,<3.0'],
    extras_require={
        'test': ['django-dynamic-fixture',
                 'docker-compose']
    }
)
