#!/usr/bin/env python3
from setuptools import setup
from os.path import abspath, dirname, join, isfile, isdir
from os import walk, path
import os


URL = "https://github.com/OpenVoiceOS/ovos-skill-speedtest"
SKILL_CLAZZ = "SpeedTestSkill"  # needs to match __init__.py class name
PYPI_NAME = "ovos-skill-speedtest"  # pip install PYPI_NAME


# below derived from github url to ensure standard skill_id
SKILL_AUTHOR, SKILL_NAME = URL.split(".com/")[-1].split("/")
SKILL_PKG = SKILL_NAME.lower().replace('-', '_')
PLUGIN_ENTRY_POINT = f'{SKILL_NAME.lower()}.{SKILL_AUTHOR.lower()}={SKILL_PKG}:{SKILL_CLAZZ}'
# skill_id=package_name:SkillClass


def find_resource_files():
    resource_base_dirs = ("locale", "gui")
    base_dir = abspath(dirname(__file__))
    package_data = ["*.json"]
    for res in resource_base_dirs:
        if isdir(join(base_dir, res)):
            for (directory, _, files) in walk(join(base_dir, res)):
                if files:
                    package_data.append(join(directory.replace(base_dir, "").lstrip('/'), '*'))
    return package_data


def get_requirements(requirements_filename: str = "requirements.txt"):
    requirements_file = join(abspath(dirname(__file__)), requirements_filename)
    if isfile(requirements_file):
        with open(requirements_file, 'r', encoding='utf-8') as r:
            requirements = r.readlines()
        requirements = [r.strip() for r in requirements if r.strip() and not r.strip().startswith("#")]
        if 'MYCROFT_LOOSE_REQUIREMENTS' in os.environ:
            print('USING LOOSE REQUIREMENTS!')
            requirements = [r.replace('==', '>=').replace('~=', '>=') for r in requirements]
        return requirements
    return []


def get_version():
    """ Find the version of this skill"""
    version_file = join(dirname(__file__), 'version.py')
    major, minor, build, alpha = (None, None, None, None)
    with open(version_file) as f:
        for line in f:
            if 'VERSION_MAJOR' in line:
                major = line.split('=')[1].strip()
            elif 'VERSION_MINOR' in line:
                minor = line.split('=')[1].strip()
            elif 'VERSION_BUILD' in line:
                build = line.split('=')[1].strip()
            elif 'VERSION_ALPHA' in line:
                alpha = line.split('=')[1].strip()

            if ((major and minor and build and alpha) or
                    '# END_VERSION_BLOCK' in line):
                break
    version = f"{major}.{minor}.{build}"
    if int(alpha):
        version += f"a{alpha}"
    return version

with open(path.join(path.abspath(path.dirname(__file__)), "README.md"), "r") as f:
    long_description = f.read()

setup(
    name=PYPI_NAME,
    version=get_version(),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url=URL,
    install_requires=get_requirements("requirements.txt"),
    author="luke5sky",
    description='OVOS speedtest skill plugin',
    license='Apache-2.0',
    package_dir={SKILL_PKG: ""},
    package_data={SKILL_PKG: find_resource_files()},
    packages=[SKILL_PKG],
    include_package_data=True,
    keywords='ovos skill plugin',
    entry_points={'ovos.plugin.skill': PLUGIN_ENTRY_POINT}
)
