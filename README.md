&nbsp;

<div align="center">

<img src="https://raw.githubusercontent.com/AgnostiqHQ/covalent/master/doc/source/_static/covalent_readme_banner.svg" width=150%>

&nbsp;

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
remote_dir = "/home/user/.cache/covalent"
ssh_key_file = "/home/user/.ssh/id_rsa"
```

This setup assumes the user has the ability to connect to the remote machine using `ssh -i /home/user/.ssh/id_rsa user@host.hostname.org` and has write-permissions on the remote directory `/home/user/.cache/covalent` (if it exists) or the closest parent directory (if it does not).

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
    remote_dir="/tmp/covalent",
    ssh_key_file="/home/user/.ssh/host2/id_rsa",
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

Covalent is licensed under the GNU Affero GPL 3.0 License. Covalent may be distributed under other licenses upon request. See the [LICENSE](https://github.com/AgnostiqHQ/covalent-ssh-plugin/blob/main/LICENSE) file or contact the [support team](mailto:support@agnostiq.ai) for more details.
