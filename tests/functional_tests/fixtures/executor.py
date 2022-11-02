from dotenv import load_dotenv

load_dotenv()

import os

import covalent as ct

executor_config = {
    "username": os.getenv("executor_username", "ubuntu"),
    "hostname": os.getenv("executor_hostname"),
    "ssh_key_file": os.getenv("executor_ssh_key_file", ""),
    "conda_env": os.getenv("executor_conda_env", "covalent"),
}

print("Using Executor Config:")
print(executor_config)

executor = ct.executor.SSHExecutor(**executor_config)
