# gen_docs

![GitHub Action status](https://github.com/christophebedard/gen_docs/workflows/Test/badge.svg)

Tool for generating documentation for ROS packages.
It currently supports doxygen and sphinx.

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

Create a configuration file, then run:

```shell
$ python3 gen_docs.py
```

For more information:

```shell
$ python3 gen_docs.py --help
```
