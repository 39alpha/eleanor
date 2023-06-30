import os
from setuptools import find_packages, setup

HERE = os.path.dirname(__file__)
with open(os.path.join(HERE, 'README.rst')) as o:
    readme = o.read()

setup(
    name='eleanor',
    version='0.0.0',
    description='Large scale aqueous geochemical modeling',
    long_description=readme,
    long_description_content_type='text/rst',
    author='39 Alpha Research',
    author_email='39alpha@39alpharesearch.org',
    license='',
    packages=find_packages(),
    package_data={'eleanor': ['data/*.csv', 'data/*.json']},
    entry_points={
        'console_scripts': ['eleanor=eleanor.command_line:combined',
                            'helmsman=eleanor.command_line:helmsman',
                            'navigator=eleanor.command_line:navigator'],
    },
    install_requires=[
        'antlr4-python3-runtime',
        'matplotlib',
        'numpy',
        'pandas',
        'scikit-learn-extra',
        'seaborn',
        'tqdm',
    ],
    setup_requires=['green'],
    test_suite='test',
    include_package_data=True,
    platforms=['OS X', 'Linux']
)
