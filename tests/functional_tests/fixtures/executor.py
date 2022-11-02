from dotenv import load_dotenv

load_dotenv()

import os

from covalent_ssh_plugin import SSHExecutor

executor_config = {
    "username": os.getenv("executor_username", "ubuntu"),
    "hostname": os.getenv("executor_hostname"),
    "ssh_key_file": os.getenv("executor_ssh_key_file", ""),
    "conda_env": os.getenv("executor_conda_env", "covalent"),
}

print("Using Executor Configuration:")
print(executor_config)

executor = SSHExecutor(**executor_config)
