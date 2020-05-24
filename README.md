# gen_docs

![GitHub Action status](https://github.com/christophebedard/gen_docs/workflows/Test/badge.svg)

Simple tool for generating documentation for ROS packages.
It currently supports doxygen and sphinx.

## What it does

It takes an input configuration as a `.yml` file:

* Repository URL
* List of versions, which must correspond to git branches
    * For each version, a list of ROS packages or an empty list
        * Each package must be a directory in the repo itself
        * If the list is empty, it will detect ROS packages (`package.yml` file in top-level directories)
        * Each package must have a valid documentation generation configuration:
            * Doxygen: `Doxyfile` under the package's directory
            * Sphinx: `docs` directory with a `Makefile` under the package's directory

e.g.

```yaml
docs:
  repo: https://github.com/my/repo.git
  versions:
    master:
    other_version:
      - packageA
      - packageB
```

## Prerequisites

Install dependencies:

```shell
$ sudo apt-get update && sudo apt-get install -y \
    python3-dev \
    python3-pip \
    git \
    doxygen
$ pip3 install -r requirements.txt
```

## Usage

Create a configuration file (e.g. `gen_docs.yml`, see [above](#What-it-does)), then run:

```shell
$ python3 gen_docs.py
```

For more information:

```shell
$ python3 gen_docs.py --help
```
