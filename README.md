# ros2_tracing-api

Tool for generating API documentation for [`ros2_tracing`](https://gitlab.com/micro-ROS/ros_tracing/ros2_tracing).

## Prerequisites

Install dependencies:

```shell
$ sudo apt-get update && sudo apt-get install -y \
    python3-dev \
    python3-pip \
    git \
    doxygen \
    python3-sphinx \
    python3-sphinx-autodoc-typehints
$ pip3 install -r requirements.txt
```

## Usage

Create or update the [configuration file](./gen_docs.yml), then run:

```shell
$ python3 gen_docs.py
```

For more information:

```shell
$ python3 gen_docs.py --help
```
