import os

import covalent as ct

from .tf_outputs import get_terraform_value

SSH_EXECUTOR_HOSTNAME = get_terraform_value("ec2_public_ip", "")

executor_config = {
    "username": os.getenv("SSH_EXECUTOR_USERNAME", "ubuntu"),
    "hostname": os.getenv("SSH_EXECUTOR_HOSTNAME", SSH_EXECUTOR_HOSTNAME),
    "ssh_key_file": os.getenv("SSH_EXECUTOR_SSH_KEY_FILE", "~/.ssh/id_rsa"),
    "python_path": os.getenv(
        "SSH_EXECUTOR_PYTHON_PATH", "/home/ubuntu/miniconda3/envs/covalent/bin/python"
    ),
}

print("Using Executor Config:")
print(executor_config)

executor = ct.executor.SSHExecutor(**executor_config)
