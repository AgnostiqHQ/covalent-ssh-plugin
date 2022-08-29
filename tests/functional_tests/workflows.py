import json
import os
import subprocess
import sys

import covalent as ct

try:
    proc = subprocess.run(
        [
            "terraform",
            "output",
            "-json",
        ],
        check=True,
        capture_output=True,
    )
    output_json = json.loads(proc.stdout.decode())
    print(output_json)
    ec2_public_ip = output_json["ec2_public_ip"]["value"]
    print(f"Got public IP: {ec2_public_ip}")
except Exception as e:
    print(e)

executor = ct.executor.SSHExecutor(
    username=os.getenv("SSH_EXECUTOR_USERNAME", "ubuntu"),
    hostname=os.getenv("SSH_EXECUTOR_HOSTNAME", "12.12.12.12"),
    ssh_key_file=os.getenv("SSH_EXECUTOR_SSH_KEY_FILE", "~/.ssh/id_rsa"),
    python_path=os.getenv(
        "SSH_EXECUTOR_PYTHON_PATH", "/home/ubuntu/miniconda3/envs/covalent/bin/python"
    ),
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
result = ct.get_result(dispatch_id=dispatch_id, wait=True)
status = str(result.status)

print(result)

if status == str(ct.status.FAILED):
    print("Basic Workflow failed to run.")
    sys.exit(1)
