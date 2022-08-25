import os
import sys

import covalent as ct

executor = ct.executor.SSHExecutor(
    username=os.getenv("SSH_EXECUTOR_USERNAME", "ubuntu"),
    hostname=os.getenv("SSH_EXECUTOR_HOSTNAME", "12.12.12.12"),
    ssh_key_file=os.getenv("SSH_EXECUTOR_SSH_KEY_FILE", "~/.ssh/id_rsa"),
    python_path=os.getenv("SSH_EXECUTOR_PYTHON_PATH", "python"),
)

# Basic Workflow


@ct.electron(executor=executor)
def join_words(a, b):
    return ", ".join([a, b])


@ct.electron
def excitement(a):
    return f"{a}!"


@ct.lattice
def basic_workflow(a, b):
    phrase = join_words(a, b)
    return excitement(phrase)


# Dispatch the workflow
dispatch_id = ct.dispatch(basic_workflow)("Hello", "World")
result = ct.get_result(dispatch_id=dispatch_id, wait=True).result

if result is None:
    sys.exit(1)
