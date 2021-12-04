import os
from setuptools import find_packages, setup

HERE = os.path.dirname(__file__)
with open(os.path.join(HERE, "README.md")) as o:
    readme = o.read()

setup(
    name='eleanor',
    version='0.0.0',
    description='large scale aqueous geochemical modelling',
    long_description=readme,
    long_description_content_type="text/markdown",
    author='39Alpha',
    author_email='tucker@39alpharesearch.org',
    packages=find_packages(),
    install_requires=["numpy", "pandas", "matplotlib"],
    license="",
    include_package_data=True
)
