# Copyright 2020 Christophe Bedard
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tool for generating documentation for ROS packages."""

import argparse
from collections import defaultdict
from io import BytesIO
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
import zipfile

import em
import requests
import yaml


data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
cppref_zip_url = 'http://upload.cppreference.com/mwiki/images/b/b2/html_book_20190607.zip'


def parse_args() -> argparse.Namespace:
    """Parse args."""
    parser = argparse.ArgumentParser(
        description='Generate Doxygen documentation for ROS packages in a repo.',
    )
    add_arguments(parser)
    return parser.parse_args()


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments to parser."""
    parser.add_argument(
        '-c', '--config',
        default='gen_docs.yml',
        help='the path to the configuration file (default: %(default)s)',
    )
    parser.add_argument(
        '-d', '--debug',
        default=False,
        action='store_true',
        help='print out stdout from commands (default: %(default)s)',
    )
    parser.add_argument(
        '--version',
        nargs='*',
        default=None,
        help=(
            'override the configuration file versions with '
            'custom versions (default: %(default)s)'
        ),
    )
    parser.add_argument(
        '-o', '--output',
        default='output',
        help=(
            'the base directory in which to put the '
            'generated documentation (default: %(default)s)'
        ),
    )
    parser.add_argument(
        '--clean',
        action='store_true',
        help='remove directories and files that might have been created by running the command',
    )


def run(
    cmd: List[str],
    cwd: Optional[str] = None,
    debug: bool = False,
) -> Tuple[subprocess.Popen, str, str]:
    """
    Run command.

    :param cmd: the command as a list
    :param cwd: the current working directory in which to run the command
    :param debug: whether to redirect stderr to stdout and combine them
    :return: (Popen object, stdout, stderr)
    """
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if debug else subprocess.PIPE,
    )
    stdout, stderr = process.communicate()
    stderr = stderr or b''
    if 0 != process.returncode:
        cmd_str = ' '.join(cmd)
        print(f"cmd '{cmd_str}' failed: {stdout.decode() if debug else stderr.decode()}")
    return process, stdout.decode(), stderr.decode()


def has_doxygen() -> bool:
    """Check if Doxygen is installed."""
    return run(['doxygen', '--help'])[0].returncode == 0


def has_sphinx() -> bool:
    """Check if Sphinx is installed."""
    return (
        run(['make', '--help'])[0].returncode == 0 and
        run(['sphinx-build', '--help'])[0].returncode == 0
    )


def run_doxygen(
    package_dir: str,
    version: Optional[str] = None,
    tagfile_rel_path: Optional[str] = None,
    cppref_tagfile_path: Optional[str] = None,
    debug: bool = False,
) -> bool:
    """
    Run doxygen for a package.

    :param package_dir: the directory of the package for which to run doxygen
    :param version: the version to be used/displayed by doxygen
        (optionally overwriting PROJECT_NUMBER)
    :param tagfile_rel_path: the relative path to the tagfile to generate
        (optionally overwriting GENERATE_TAGFILE)
    :param cppref_tagfile_path: the path to a cpp reference tagfile
        (optionally adding to TAGFILES)
    :param debug: whether to print stdout
    :return: True if successful, False otherwise
    """
    # Append options to Doxyfile to overwrite the current values
    if version or tagfile_rel_path or cppref_tagfile_path:
        print('\t\tAppending parameters:')
        doxyfile_path = os.path.join(package_dir, 'Doxyfile')
        with open(doxyfile_path, 'a') as doxyfile:
            if version:
                param = f'PROJECT_NUMBER = "{version}"'
                print('\t\t\t' + param)
                doxyfile.write(param + '\n')
            if tagfile_rel_path:
                param = f'GENERATE_TAGFILE = "{tagfile_rel_path}"'
                print('\t\t\t' + param)
                doxyfile.write(param + '\n')
            if cppref_tagfile_path:
                param = f'TAGFILES += "{cppref_tagfile_path}=http://en.cppreference.com/w/"'
                print('\t\t\t' + param)
                doxyfile.write(param + '\n')
    rc, stdout, _ = run(['doxygen'], package_dir, debug)
    if 0 != rc.returncode:
        return False
    if debug:
        print(stdout)
    return True


def run_sphinx(
    package_dir: str,
    version: Optional[str] = None,
    release: Optional[str] = None,
    debug: bool = False,
) -> bool:
    """
    Run sphinx for a package.

    :param package_dir: the directory of the package for which run sphinx
    :param version: the version name to be used/displayed by sphinx
        (optionally overwriting 'version')
    :param release: the release name to be used/displayed by sphinx
        (optionally overwriting 'release')
    :param debug: whether to print stdout
    :return: True if successful, False otherwise
    """
    os.environ['SPHINX_VERSION_FULL'] = version
    os.environ['SPHINX_VERSION_SHORT'] = version
    if version or release:
        print('\t\tAppending parameters:')
        conf_file_path = os.path.join(package_dir, 'docs', 'source', 'conf.py')
        with open(conf_file_path, 'a') as conf:
            if version:
                param = f"version = '{version}'"
                print('\t\t\t' + param)
                conf.write(param + '\n')
            if release:
                param = f"release = '{release}'"
                print('\t\t\t' + param)
                conf.write(param + '\n')
    # The Makefile is under docs/
    make_path = os.path.join(package_dir, 'docs')
    rc, stdout, _ = run(['make', 'html'], make_path, debug)
    if 0 != rc.returncode:
        return False
    if debug:
        print(stdout)
    return True


def expand_template_file(
    template_file_name: str,
    dest_file_path: str,
    data: Dict[str, Any],
) -> Optional[str]:
    """
    Expand template file.

    :param template_file_name: the name of the template file to use (in data/)
    :param dest_file_path: the file path
    :return: the path of the created file, or None if it failed
    """
    template_file_path = os.path.join(data_dir, template_file_name)
    template = None
    with open(template_file_path, 'r') as f:
        template = f.read()
    if template is None:
        return None
    written = 0
    with open(dest_file_path, 'w') as f:
        written = f.write(em.expand(template, data))
    if 0 >= written:
        return None
    return dest_file_path


def create_html_redirect_file(
    relative_url: str,
    dest: str,
) -> Optional[str]:
    """
    Create HTML redirect file.

    :param relative_url: the relative URL to redirect to
    :param dest: the destination directory in which to put the file
    :return: the path of the created file, or None if it failed
    """
    redirect_file = os.path.join(dest, 'index.html')
    return expand_template_file('redirect.html', redirect_file, {'url': relative_url})


def create_packages_list_file(
    repo_name: str,
    version: str,
    packages: List[str],
    dest: str,
    other_versions: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Create packages list file.

    :param repo_name: the name of the repository containing the packages
    :param version: the version/branch of these packages
    :param packages: the list of packages
    :param dest: the destination directory in which to put the file
    :param other_versions: the list of other versions to link to
    :return: the path of the created file, or None if it failed
    """
    packages_list_file = os.path.join(dest, 'index.html')
    timestamp = time.strftime('on %Y-%m-%d at %H:%M:%S +0000', time.gmtime())
    return expand_template_file(
        'packages_list.html',
        packages_list_file,
        {
            'repo_name': repo_name,
            'version': version,
            'packages': packages,
            'other_versions': other_versions,
            'timestamp': timestamp,
        },
    )


def download_zip_file(
    url: str,
) -> Optional[zipfile.ZipFile]:
    """
    Download and get ZIP file.

    :param url: the URL of the ZIP file to download
    :return: a ZipFile object with the downloaded data, or None if it failed
    """
    r = requests.get(url, stream=True)
    if not r.ok:
        print('Request failed:', url)
        return None
    return zipfile.ZipFile(BytesIO(r.content))


def extract_file_from_zip(
    zip_file: zipfile.ZipFile,
    internal_file_path: str,
    dest: str,
) -> str:
    """
    Extract file from ZIP and copy it to a directory.

    :param zip_file: the ZipFile object
    :param internal_file_path: the internal path (inside the ZIP) of the file to extract
    :param dest: the directory to copy the file into
    :return: the path of the extracted file
    """
    return zip_file.extract(internal_file_path, path=dest)


def download_zip_file_and_extract(
    url: str,
    internal_file_path: str,
    dest: str,
    skip_if_exists: bool = True,
) -> Optional[str]:
    """
    Download ZIP and extract file to directory.

    :param url: the URL of the ZIP file to download
    :param internal_file_path: the internal path (inside the ZIP) of the file to extract
    :param dest: the directory to copy the file into
    :param skip_if_exists: whether to skip downloading/extracting if destination file exists
    :return: the path of the extracted file, or None if it failed
    """
    dest_file_path = os.path.join(dest, internal_file_path)
    if skip_if_exists and os.path.exists(dest_file_path):
        print('\tSkipping since it exists')
        return dest_file_path
    zip_ = download_zip_file(url)
    if not zip_:
        return None
    extracted_file_path = extract_file_from_zip(
        zip_,
        internal_file_path,
        dest,
    )
    return extracted_file_path


def clone_repo(
    url: str,
    path: str,
    branch: Optional[str] = None,
) -> bool:
    """Clone repo from URL (at branch if specified) to given path."""
    cmd = ['git', 'clone', url, path]
    if branch:
        cmd += ['--branch', branch]
    return run(cmd)[0].returncode == 0


def get_repo_name_from_url(
    repo_url: str,
    default_version: str,
    valid: Dict[str, List[str]],
) -> str:
    """
    Extract repository name from URL.

    If it cannot be extracted, the name of the first package of the default version is used.

    :param repo_url: the repository URL
    :param default_version: the default version
    :param valid: the dictionary of valid versions & packages
    :return: the repo name, or a default package if it failed
    """
    repo_name = None
    repo_name_match = re.match('.*/(.*)$', repo_url)
    if repo_name_match:
        # Remove '.git' extension if it is there
        repo_name = repo_name_match[1].replace('.git', '')
    else:
        # Default to first package of first version
        repo_name = valid[default_version][0]
    return repo_name


def load_config(
    path: str = 'gen_docs.yml',
) -> Optional[Dict]:
    """Load configuration from file."""
    config = None
    with open(path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def is_valid_config(
    config: Dict,
) -> bool:
    """Validate configuration."""
    docs = config.get('docs', None)
    if not docs:
        print("Missing top-level 'docs' key")
        return False
    repo = docs.get('repo', None)
    if not repo:
        print("Missing 'repo' under 'docs'")
        return False
    versions = docs.get('versions', None)
    if not versions:
        print("Missing 'versions' under 'docs'")
        return False
    for version_name, packages in versions.items():
        if not isinstance(version_name, str):
            print('Versions have to be strings. Invalid version(s):', version_name)
            return False
        if packages:
            # Convert string to list if necessary
            packages = [packages] if not isinstance(packages, list) else packages
            versions[version_name] = packages
            if any(not isinstance(package, str) for package in packages):
                print('Packages have to be strings. Invalid package(s):', packages)
                return False
    return True


def get_packages(
    path: str,
) -> List[str]:
    """Get list of packages under a path."""
    packages = []
    for file_or_dir in os.listdir(path):
        file_or_dir_path = os.path.join(path, file_or_dir)
        if os.path.isdir(file_or_dir_path):
            dir_name = file_or_dir
            dir_path = file_or_dir_path
            if (
                not dir_name.startswith('.') and
                os.path.exists(os.path.join(dir_path, 'package.xml'))
            ):
                packages.append(dir_name)
    return packages


def get_package_docs_type(
    package_dir: str,
) -> Optional[str]:
    """
    Identify a package's documentation generation type.

    :param package_dir: the directory of the package
    :return: the docs type ('doxygen', 'sphinx') or None if it failed
    """
    if os.path.exists(os.path.join(package_dir, 'Doxyfile')):
        return 'doxygen'
    # For now a Makefile implies sphinx
    if os.path.exists(os.path.join(package_dir, 'docs', 'Makefile')):
        return 'sphinx'
    return None


def get_package_version(
    package_xml_path: str,
) -> Optional[str]:
    """
    Get a package's version from its package.xml file.

    :param package_xml_path: the path to the package's package.xml file
    :return: the version, or None if it failed
    """
    version = None
    with open(package_xml_path, 'r') as package_xml_file:
        content = package_xml_file.read()
        version_match = re.match(r'.*<version>(.*)<\/version>.*', content, flags=re.DOTALL)
        if version_match:
            version = version_match.group(1)
    return version


def main() -> int:
    """Run main logic."""
    args = parse_args()
    custom_versions = args.version
    debug = args.debug
    output_dir = os.path.join(os.path.curdir, args.output)
    repos_dir = os.path.join(os.path.curdir, 'repos')
    artifact_dirs = [output_dir, repos_dir]

    # Clean if option is enabled or if artifact directories exist
    if (
        args.clean or
        any(os.path.exists(artifact_dir) for artifact_dir in artifact_dirs)
    ):
        print('Cleaning up')
        for artifact_dir in artifact_dirs:
            print(f"\tRemoving '{artifact_dir}'")
            shutil.rmtree(artifact_dir, ignore_errors=True)
        if args.clean:
            return 0
        else:
            print()

    # Check that doxygen is installed
    if not has_doxygen():
        print('Could not find doxygen')
        return 1
    # Check that sphinx is installed
    if not has_sphinx():
        print('Could not find sphinx')
        return 1

    # Load config and validate
    config = load_config(args.config)
    if not is_valid_config(config):
        return 1
    if custom_versions:
        config['docs']['versions'] = {version: None for version in custom_versions}
    print('Configuration:')
    for version, packages in config['docs']['versions'].items():
        packages_list = ', '.join(packages) if packages else ''
        print(
            f"\t{version}{f': {packages_list}' if packages_list else ' (all)'}"
            f"{' (overriden)' if custom_versions else ''}"
        )

    print()

    # Download cppreference file
    print('Downloading cppreference tag file')
    cppref_tagfile_name = 'cppreference-doxygen-web.tag.xml'
    if not download_zip_file_and_extract(
        cppref_zip_url,
        cppref_tagfile_name,
        data_dir,
    ):
        return 1
    cppref_tagfile_path = os.path.join(data_dir, cppref_tagfile_name)

    print()

    # Process repos
    repo_url = config['docs']['repo']
    # Insert GitHub token if one is provided through the environment
    if 'GITHUB_TOKEN' in os.environ:
        print('Using GITHUB_TOKEN')
        repo_url = repo_url.replace(
            'https://github.com',
            f'https://{os.environ["GITHUB_TOKEN"]}@github.com',
        )
    valid = defaultdict(list)
    for version, packages in config['docs']['versions'].items():
        # Clone repo @ branch
        print(f"Cloning repo at version '{version}'")
        repo_dir = os.path.join(repos_dir, version)
        if not clone_repo(repo_url, repo_dir, branch=version):
            return 1

        # If no packages are given, search for packages in the repo
        if not packages:
            packages = get_packages(repo_dir)
            if not packages:
                print(f"Could not find any packages for version '{version}', skipping")
                continue
            print(f'\tFound packages: {packages}')
        version_output_dir = os.path.join(output_dir, version)
        # Process packages
        for package in packages:
            package_dir = os.path.join(repo_dir, package)
            # Detect the package's docs type
            docs_output_dir = None
            docs_type = get_package_docs_type(package_dir)
            if not docs_type:
                print(f"\tCould not find documentation for package '{package}'")
                continue
            # Run docs generation
            print(f"\tRunning {docs_type} for package '{package}'")
            if 'doxygen' == docs_type:
                package_tagfile_path = os.path.join(data_dir, package + '.tag')
                if not run_doxygen(
                    package_dir,
                    version=version,
                    tagfile_rel_path=package_tagfile_path,
                    cppref_tagfile_path=cppref_tagfile_path,
                    debug=debug,
                ):
                    return 1
                docs_output_dir = os.path.join(package_dir, 'doc_output', 'html')
            elif 'sphinx' == docs_type:
                package_xml_path = os.path.join(package_dir, 'package.xml')
                if not run_sphinx(
                    package_dir,
                    version=version,
                    release=get_package_version(package_xml_path),
                    debug=debug,
                ):
                    return 1
                docs_output_dir = os.path.join(package_dir, 'docs', 'build', 'html')
            else:
                print(f"\tUnknown docs type '{docs_type}' for package '{package}'")
                continue
            assert docs_output_dir
            # Move output
            public_package_dir = os.path.join(version_output_dir, package)
            shutil.move(docs_output_dir, public_package_dir)
            # Remember that this package is valid
            valid[version].append(package)

    print()

    if not valid:
        print('Warning: did not generate any documentation')
        return 0
    # Create packages list for each version
    default_version = list(valid.keys())[0]
    repo_name = get_repo_name_from_url(repo_url, default_version, valid)
    for version, packages in valid.items():
        other_versions = set(valid.keys())
        other_versions.remove(version)
        packages_list_file = create_packages_list_file(
            repo_name,
            version,
            packages,
            os.path.join(output_dir, version),
            other_versions,
        )
        if not packages_list_file:
            print(f"Failed to create packages list file for version '{version}'")
            return 1
    # Create redirect to default version (first one in the list)
    print(f"Creating redirection file to default version '{default_version}'")
    main_index_file = create_html_redirect_file(default_version, output_dir)
    if not main_index_file:
        print('Failed to create redirection file to default version')
        return 1
    print()
    print(f'Generation done: file://{os.path.abspath(main_index_file)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
