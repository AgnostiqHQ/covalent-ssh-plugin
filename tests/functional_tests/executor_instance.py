import os

import covalent as ct
import terraform_output

hostname = os.getenv("SSH_EXECUTOR_HOSTNAME") or terraform_output.get("ec2_public_ip", "")
username = os.getenv("SSH_EXECUTOR_USERNAME", "ubuntu")
ssh_key_file = os.getenv("SSH_EXECUTOR_SSH_KEY_FILE", "")
conda_env = os.getenv("SSH_EXECUTOR_CONDA_ENV", "covalent")

executor_config = {
    "username": username,
    "hostname": hostname,
    "ssh_key_file": ssh_key_file,
    "conda_env": conda_env,
}

print("Using Executor Config:")
print(executor_config)

executor = ct.executor.SSHExecutor(**executor_config)
