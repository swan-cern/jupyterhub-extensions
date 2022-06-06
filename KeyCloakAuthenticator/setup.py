import os

from jupyter_packaging import get_version
import setuptools

name="keycloakauthenticator"

# Get our version
version = get_version(os.path.join(name, "_version.py"))


with open("README.md", "r") as fh:
    long_description = fh.read()

setup_args = dict(
    name=name,
    version=version,
    url="https://github.com/swan-cern/jupyterhub-extensions",
    author="SWAN Admins",
    description="KeyCloakAuthenticator: Authenticate JupyterHub users with KeyCloak and OIDC",
    long_description= long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    install_requires=[
        'jupyterhub',
        'oauthenticator==15.0.0',
        'PyJWT[crypto]>=2.0.0'
    ],
    zip_safe=False,
    include_package_data=True,
    license="AGPL-3.0",
    platforms="Linux, Mac OS X",
    keywords=["JupyterHub", "Authenticator", "SWAN", "CERN"],
    classifiers=[
        "License :: OSI Approved :: GNU Affero General Public License v3",
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Science/Research',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
)


if __name__ == "__main__":
    setuptools.setup(**setup_args)
