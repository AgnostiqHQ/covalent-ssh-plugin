# Copyright 2021 Agnostiq Inc.
#
# This file is part of Covalent.
#
# Licensed under the GNU Affero General Public License 3.0 (the "License").
# A copy of the License may be obtained with this software package or at
#
#      https://www.gnu.org/licenses/agpl-3.0.en.html
#
# Use of this file is prohibited except in compliance with the License. Any
# modifications or derivative works of this file must retain this copyright
# notice, and modified files must contain a notice indicating that they have
# been altered from the originals.
#
# Covalent is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the License for more details.
#
# Relief from the License may be granted by purchasing a commercial license.

"""
Executor plugin for executing the function on a remote machine through SSH.
"""

import os
import socket
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, Tuple, Union

import asyncssh
import cloudpickle as pickle
from covalent._results_manager.result import Result
from covalent._shared_files import logger
from covalent._shared_files.config import get_config, update_config
from covalent.executor.base import BaseAsyncExecutor

executor_plugin_name = "SSHExecutor"

app_log = logger.app_log
log_stack_info = logger.log_stack_info

_EXECUTOR_PLUGIN_DEFAULTS = {
    "username": "",
    "hostname": "",
    "ssh_key_file": os.path.join(os.environ["HOME"], ".ssh/id_rsa"),
    "cache_dir": str(Path(get_config("dispatcher.cache_dir")).expanduser().resolve()),
    "remote_cache_dir": ".cache/covalent",
    "python_path": "python",
    "run_local_on_ssh_fail": False,
    "conda_env": "",
}


class SSHExecutor(BaseAsyncExecutor):
    """
    Async executor class that invokes the input function on a remote server.

    Args:
        username: Username used to authenticate over SSH.
        hostname: Address or hostname of the remote server.
        ssh_key_file: Filename of the private key used for authentication with the remote server.
        cache_dir: Local cache directory used by this executor for temporary files.
        remote_cache_dir: Remote server cache directory used for temporary files.
        python_path: The path to the Python 3 executable on the remote server.
        run_local_on_ssh_fail: If True, and the execution fails to run on the remote server,
            then the execution is run on the local machine.
        kwargs: Key-word arguments to be passed to the parent class (BaseExecutor)
    """

    def __init__(
        self,
        username: str,
        hostname: str,
        ssh_key_file: str,
        cache_dir: str = None,
        python_path: str = "",
        conda_env: str = None,
        remote_cache_dir: str = "",
        run_local_on_ssh_fail: bool = False,
        do_cleanup: bool = True,
        **kwargs,
    ) -> None:

        super().__init__(**kwargs)

        self.username = username or get_config("executors.ssh.username")
        self.hostname = hostname or get_config("executors.ssh.hostname")
        self.remote_cache_dir = (
            remote_cache_dir or get_config("executors.ssh.remote_cache_dir") or ".cache/covalent"
        )
        self.python_path = python_path or get_config("executors.ssh.python_path") or "python"
        self.conda_env = conda_env or get_config("executors.ssh.conda_env")

        ssh_key_file = ssh_key_file or get_config("executors.ssh.ssh_key_file")
        self.ssh_key_file = str(Path(ssh_key_file).expanduser().resolve())

        self.cache_dir = cache_dir or get_config("dispatcher.cache_dir")
        self.cache_dir = str(Path(self.cache_dir).expanduser().resolve())

        self.run_local_on_ssh_fail = run_local_on_ssh_fail
        self.do_cleanup = do_cleanup

    def _write_function_files(
        self,
        operation_id: str,
        fn: Callable,
        args: list,
        kwargs: dict,
    ) -> None:
        """
        Helper function to pickle the function to be executoed to file, and write the
            python script which calls the function.

        Args:
            operation_id: A concatenation of the dispatch ID and task ID.
            fn: The input python function which will be executed and whose result
                is ultimately returned by this function.
            args: List of positional arguments to be used by the function.
            kwargs: Dictionary of keyword arguments to be used by the function.
        """

        # Pickle and save location of the function and its arguments:
        function_file = os.path.join(self.cache_dir, f"function_{operation_id}.pkl")

        with open(function_file, "wb") as f_out:
            pickle.dump((fn, args, kwargs), f_out)
        remote_function_file = os.path.join(self.remote_cache_dir, f"function_{operation_id}.pkl")

        # Write the code that the remote server will use to execute the function.

        message = f"Function file names:\nLocal function file: {function_file}\n"
        message += f"Remote function file: {remote_function_file}"
        app_log.debug(message)

        remote_result_file = os.path.join(self.remote_cache_dir, f"result_{operation_id}.pkl")
        exec_script = "\n".join(
            [
                "import sys",
                "",
                "result = None",
                "exception = None",
                "",
                "try:",
                "    import cloudpickle as pickle",
                "except Exception as e:",
                "    import pickle",
                f"    with open('{remote_result_file}','wb') as f_out:",
                "        pickle.dump((None, e), f_out)",
                "        exit()",
                "",
                f"with open('{remote_function_file}', 'rb') as f_in:",
                "    fn, args, kwargs = pickle.load(f_in)",
                "    try:",
                "        result = fn(*args, **kwargs)",
                "    except Exception as e:",
                "        exception = e",
                "",
                f"with open('{remote_result_file}','wb') as f_out:",
                "    pickle.dump((result, exception), f_out)",
                "",
            ]
        )
        script_file = os.path.join(self.cache_dir, f"exec_{operation_id}.py")
        remote_script_file = os.path.join(self.remote_cache_dir, f"exec_{operation_id}.py")
        with open(script_file, "w") as f_out:
            f_out.write(exec_script)

        return (
            function_file,
            script_file,
            remote_function_file,
            remote_script_file,
            remote_result_file,
        )

    def _on_ssh_fail(
        self,
        fn: Callable,
        args: list,
        kwargs: dict,
        message: str,
    ) -> Union[Tuple[Any, str, str], None]:
        """
        Handles what happens when executing the function on the remote host fails.

        Args:
            fn: The function to be executed.
            kwargs: The input arguments to the function.
            message: The warning/error message to be displayed.

        Returns:
            Either:
                a) the function result if self.run_local_on_ssh_fail == True, or
                b) None and raise RuntimeError if self.run_local_on_ssh_fail == False.
        """

        if self.run_local_on_ssh_fail:
            app_log.warning(message)
            return fn(*args, **kwargs)

        else:
            app_log.error(message)
            raise RuntimeError(message)

    async def _client_connect(self) -> bool:
        """
        Helper function for connecting to the remote host through the paramiko module.

        Args:
            None

        Returns:
            True if connection to the remote host was successful, False otherwise.
        """

        ssh_success = False
        conn = None
        if os.path.exists(self.ssh_key_file):
            try:
                conn = await asyncssh.connect(
                    self.hostname,
                    username=self.username,
                    client_keys=[self.ssh_key_file],
                    known_hosts=None,
                )

                ssh_success = True
            except (socket.gaierror, ValueError, TimeoutError) as e:
                app_log.error(e)

        else:
            message = f"no SSH key file found at {self.ssh_key_file}. Cannot connect to host."
            app_log.error(message)

        return ssh_success, conn

    def get_status(self, info_dict: dict) -> Result:
        """
        Get the current status of the task.

        Args:
            info_dict: a dictionary containing any neccessary parameters needed to query the
                status. For this class (LocalExecutor), the only info is given by the
                "STATUS" key in info_dict.

        Returns:
            A Result status object (or None, if "STATUS" is not in info_dict).
        """

        return info_dict.get("STATUS", Result.NEW_OBJ)

    async def cleanup(
        self,
        conn,
        function_file,
        script_file,
        result_file,
        remote_function_file,
        remote_script_file,
        remote_result_file,
    ):
        """
        Perform cleanup of created files

        Args:
            conn:
            function_file:
            script_file:
            result_file:
            remote_function_file:
            remote_script_file:
            remote_result_file:

        Returns:
            None
        """

        os.remove(function_file)
        os.remove(script_file)
        os.remove(result_file)
        await conn.run(f"rm {remote_function_file}")
        await conn.run(f"rm {remote_script_file}")
        await conn.run(f"rm {remote_result_file}")

    async def run(
        self, function: Callable, args: list, kwargs: dict, task_metadata: Dict
    ) -> Coroutine:
        """
        Run the executable on remote machine and return the result.

        Args:
            function: Function to be run on the remote machine.
            args: Positional arguments to be passed to the function.
            kwargs: Keyword argument to be passed to the function.

        Returns:
            An awaitable coroutine which once awaited will return the result
            of the executed function.
        """

        dispatch_id = task_metadata["dispatch_id"]
        node_id = task_metadata["node_id"]
        operation_id = f"{dispatch_id}_{node_id}"

        exception = None

        ssh_success, conn = await self._client_connect()

        if not ssh_success:
            message = f"Could not connect to host: '{self.hostname}' as user: '{self.username}'"
            return self._on_ssh_fail(function, args, kwargs, message)

        message = (
            f"Executing node {node_id} on host {self.hostname} with username {self.username}."
        )
        app_log.debug(message)

        if self.conda_env:
            app_log.debug(f"Verifying if conda env {self.conda_env} exists")
            completed_proc = await conn.run(f"conda env list | grep {self.conda_env}")

            if completed_proc.returncode != 0:
                message = (
                    completed_proc.stderr.strip()
                    or f"No conda environment named {self.conda_env} found on remote machine."
                )
                return self._on_ssh_fail(function, args, kwargs, message)

        version_check = await conn.run(f"{self.python_path} --version")
        if "3" not in version_check.stdout.strip():
            message = f"No Python 3 installation found on remote machine {self.hostname}"
            return self._on_ssh_fail(function, args, kwargs, message)

        app_log.debug(f"Remote python being used is {self.python_path}")

        cmd = f"mkdir -p {self.remote_cache_dir}"

        mkdir_cache = await conn.run(cmd)
        client_out = mkdir_cache.stdout
        if client_err := mkdir_cache.stderr:
            app_log.warning(client_err)

        # Pickle and save location of the function and its arguments:
        (
            function_file,
            script_file,
            remote_function_file,
            remote_script_file,
            remote_result_file,
        ) = self._write_function_files(operation_id, function, args, kwargs)

        app_log.debug("Copying function file to remote machine...")

        await asyncssh.scp(function_file, (conn, remote_function_file))
        await asyncssh.scp(script_file, (conn, remote_script_file))

        app_log.debug("Running function file in remote machine...")

        # Run the function:
        cmd = f"{self.python_path} {remote_script_file}"

        if self.conda_env:
            cmd = f"conda activate {self.conda_env} && {cmd}"

        app_log.debug(f"Running the function on remote now with command: {cmd}")
        result = await conn.run(cmd)
        app_log.debug("Function run finished")

        if result_err := result.stderr.strip():
            app_log.warning(result_err)
            return self._on_ssh_fail(function, args, kwargs, result_err)

        app_log.debug("Checking that result file was produced in remote machine...")

        # Check that a result file was produced:
        app_log.debug("Checking result file was produced")
        cmd = f"ls {remote_result_file}"
        check_result_file = await conn.run(cmd)
        client_out = check_result_file.stdout
        if client_out.strip() != remote_result_file:
            message = (
                f"Result file {remote_result_file} on remote host {self.hostname} was not found"
            )
            return self._on_ssh_fail(function, args, kwargs, message)

        # scp the pickled result to the local machine here:
        result_file = os.path.join(self.cache_dir, f"result_{operation_id}.pkl")

        app_log.debug(f"Copying result file from remote machine to local path {result_file}...")
        await asyncssh.scp((conn, remote_result_file), result_file)

        # Load the result file:
        app_log.debug("Loading result file")
        with open(result_file, "rb") as f_in:
            result, exception = pickle.load(f_in)

        if self.do_cleanup:
            app_log.debug("Performing cleanup on local and remote")
            await self.cleanup(
                conn=conn,
                function_file=function_file,
                script_file=script_file,
                result_file=result_file,
                remote_function_file=remote_function_file,
                remote_script_file=remote_script_file,
                remote_result_file=remote_result_file,
            )

        if exception is not None:
            app_log.debug(f"exception: {exception}")
            raise exception

        app_log.debug("Closing SSH connection...")
        conn.close()
        await conn.wait_closed()

        app_log.debug("SSH Connection closed. SSH executor run finished. Returning result file...")

        return result
