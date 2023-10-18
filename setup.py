from subprocess import check_output

from setuptools import find_packages, setup

requirements = []
with open('./requirements.txt') as f:
    lines = f.read().splitlines()
    for line in lines:
        if not line.startswith('git+ssh'):
            requirements.append(line)

test_requirements = []
with open('./requirements-dev.txt') as f:
    lines = f.read().splitlines()
    for line in lines:
        if not line.startswith('git+ssh'):
            test_requirements.append(line)

try:
    version = (
        check_output(['git', 'describe', '--tags']).rstrip().decode().replace('v', '')
    )
except Exception as e:
    print(e)
    version = '1.0.0'


setup(
    author='akquinet',
    author_email='noc@akquinet.de',
    python_requires='>=3.8',
    description='PowerDNS-API-Proxy',
    install_requires=requirements,
    include_package_data=True,
    keywords='powerdns_api_proxy',
    name='powerdns_api_proxy',
    packages=find_packages(include=['powerdns_api_proxy', 'powerdns_api_proxy.*']),
    test_suite='tests',
    tests_require=test_requirements,
    version=version,
    zip_safe=False,
)
