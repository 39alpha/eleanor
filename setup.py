import os
from setuptools import find_packages, setup

HERE = os.path.dirname(__file__)
with open(os.path.join(HERE, 'README.rst')) as o:
    readme = o.read()

setup(
    name='eleanor',
    version='0.0.0',
    description='large scale aqueous geochemical modelling',
    long_description=readme,
    long_description_content_type='text/rst',
    author='39Alpha',
    author_email='tucker@39alpharesearch.org',
    license='',
    packages=find_packages(),
    package_data={'eleanor': ['data/*.csv', 'data/*.json']},
    entry_points={
        'console_scripts': ['eleanor=eleanor.command_line:combined',
                            'helmsman=eleanor.command_line:helmsman',
                            'navigator=eleanor.command_line:navigator'],
    },
    install_requires=['matplotlib', 'numpy', 'pandas', 'antlr4-python3-runtime'],
    setup_requires=['green'],
    test_suite='test',
    include_package_data=True,
    platforms=['OS X', 'Linux']
)
