import sys
from setuptools import find_packages, setup

setup(
    name='DjangoInelasticModels',
    version='1.4.4',
    author='Thom Linton',
    author_email='tlinton@pdx.edu',
    url='https://github.com/PSU-OIT-ARC/django-inelastic-models',
    long_description=open('README.rst').read(),

    packages=find_packages(),
    install_requires=['elasticsearch>=2.0.0,<5.0.0',
                      'elasticsearch-dsl>=2.0.0,<5.0.0'],
    extras_require={
        'test': ['django>1.11', 'django-dynamic-fixture']
    }
)
