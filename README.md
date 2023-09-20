&nbsp;

<div align="center">

<img src="https://raw.githubusercontent.com/AgnostiqHQ/covalent-ssh-plugin/main/assets/ssh_readme_banner.jpg" width=150%>

[![covalent](https://img.shields.io/badge/covalent-0.177.0-purple)](https://github.com/AgnostiqHQ/covalent)
[![python](https://img.shields.io/pypi/pyversions/covalent-ssh-plugin)](https://github.com/AgnostiqHQ/covalent-ssh-plugin)
[![tests](https://github.com/AgnostiqHQ/covalent-ssh-plugin/actions/workflows/tests.yml/badge.svg)](https://github.com/AgnostiqHQ/covalent-ssh-plugin/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/AgnostiqHQ/covalent-ssh-plugin/branch/main/graph/badge.svg?token=QNTR18SR5H)](https://codecov.io/gh/AgnostiqHQ/covalent-ssh-plugin)
[![apache](https://img.shields.io/badge/License-Apache_License_2.0-blue)](https://www.apache.org/licenses/LICENSE-2.0)

</div>

## Covalent SSH Plugin

Covalent is a Pythonic workflow tool used to execute tasks on advanced computing hardware. This executor plugin interfaces Covalent with other machines accessible to the user over SSH. It is appropriate to use this plugin to distribute tasks to one or more compute backends which are not controlled by a cluster management system, such as computers on a LAN, or even a collection of small-form-factor Linux-based devices such as Raspberry Pis, NVIDIA Jetsons, or Xeon Phi co-processors.

To use this plugin with Covalent, simply install it using `pip`:

```shell
pip install covalent-ssh-plugin
```

The following shows an example of how a user might modify their Covalent [configuration](https://covalent.readthedocs.io/en/latest/how_to/config/customization.html) to support this plugin:

```shell
[executors.ssh]
username = "user"
hostname = "host.hostname.org"
remote_cache_dir = "/home/user/.cache/covalent"
ssh_key_file = "/home/user/.ssh/id_rsa"
python_path = "python"
conda_env = ""
```

This setup assumes the user has the ability to connect to the remote machine using `ssh -i /home/user/.ssh/id_rsa user@host.hostname.org` and has write-permissions on the remote directory `/home/user/.cache/covalent` (if it exists) or the closest parent directory (if it does not).

If you are using a named conda environment you can use the `conda_env` parameter to set the name of your conda environment. However if you wish use a specify a particular python binary you can configure the `python_path` parameter to the absolute path where python is located on the remote machine.

Within a workflow, users can decorate electrons using the default settings:

```python
import covalent as ct

@ct.electron(executor="ssh")
def my_task():
    import socket
    return socket.gethostname()
```

or use a class object to customize behavior within particular tasks:

```python
executor = ct.executor.SSHExecutor(
    username="user",
    hostname="host2.hostname.org",
    remote_cache_dir="/tmp/covalent",
    ssh_key_file="/home/user/.ssh/host2/id_rsa"
)

@ct.electron(executor=executor)
def my_custom_task(x, y):
    return x + y
```

For more information on how to get started with Covalent, check out the project [homepage](https://github.com/AgnostiqHQ/covalent) and the official [documentation](https://covalent.readthedocs.io/en/latest/).

## Release Notes

Release notes are available in the [Changelog](https://github.com/AgnostiqHQ/covalent-ssh-plugin/blob/main/CHANGELOG.md).

## Citation

Please use the following citation in any publications:

> W. J. Cunningham, S. K. Radha, F. Hasan, J. Kanem, S. W. Neagle, and S. Sanand.
> *Covalent.* Zenodo, 2022. https://doi.org/10.5281/zenodo.5903364

## License

Covalent is licensed under the Apache License 2.0. See the [LICENSE](https://github.com/AgnostiqHQ/covalent-ssh-plugin/blob/main/LICENSE) file or contact the [support team](mailto:support@agnostiq.ai) for more details.
