import sys
from setuptools import find_packages, setup

setup(
    name='DjangoInelasticModels',
    version='1.1',
    install_requires=['elasticsearch>=2.0.0,<5.0.0','elasticsearch-dsl>=2.0.0,<5.0.0'],
    packages=find_packages(),
    long_description=open('README.rst').read(),
    author='Thom Linton',
    extras_require={
        'test': ["django" + ("<1.7" if sys.version_info[:2] < (2, 7) else ""),
                 'django-dynamic-fixture'],
    }
)
