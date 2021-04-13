import sys
from setuptools import find_packages, setup

setup(
    name='DjangoInelasticModels',
    version='1.5.0',
    author='Thom Linton',
    author_email='tlinton@pdx.edu',
    url='https://github.com/PSU-OIT-ARC/django-inelastic-models',
    long_description=open('README.rst').read(),
    license='MIT',
    packages=find_packages(),
    install_requires=['elasticsearch~=7.0',
                      'elasticsearch-dsl~=7.0',
                      'django>2.2,<3.0'],
    extras_require={
        'test': ['django-dynamic-fixture',
                 'docker-compose']
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Topic :: Software Development :: Build Tools',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ]
)
