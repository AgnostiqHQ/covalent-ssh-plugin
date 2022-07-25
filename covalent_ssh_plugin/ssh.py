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

# Required for all executor plugins
import os
import socket
from contextlib import redirect_stderr, redirect_stdout
from multiprocessing import Queue as MPQ
from typing import Any, Callable, Tuple, Union, Coroutine, List, Dict

# Executor-specific imports:
import sys
import asyncssh
import cloudpickle as pickle

# Covalent imports
from covalent._results_manager.result import Result
from covalent._shared_files import logger
from covalent._shared_files.config import get_config, update_config
from covalent._shared_files.util_classes import DispatchInfo
from covalent._workflow.transport import TransportableObject
from covalent.executor.base import BaseAsyncExecutor

# The plugin class name must be given by the EXECUTOR_PLUGIN_NAME attribute:
executor_plugin_name = "SSHExecutor"

app_log = logger.app_log
log_stack_info = logger.log_stack_info

_EXECUTOR_PLUGIN_DEFAULTS = {
    "username": "",
    "hostname": "",
    "ssh_key_file": os.path.join(os.environ["HOME"], ".ssh/id_rsa"),
    "cache_dir": os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ["HOME"], ".cache"), "covalent"
    ),
    "remote_cache_dir": ".cache/covalent",
    "python3_path": "",
    "run_local_on_ssh_fail": False,
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
        python3_path: The path to the Python 3 executable on the remote server.
        run_local_on_ssh_fail: If True, and the execution fails to run on the remote server,
            then the execution is run on the local machine.
        kwargs: Key-word arguments to be passed to the parent class (BaseExecutor)
    """

    def __init__(
        self,
        username: str,
        hostname: str,
        ssh_key_file: str = os.path.join(os.environ["HOME"], ".ssh/id_rsa"),
        cache_dir: str = os.path.join(
            os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ["HOME"], ".cache"),
            "covalent",
        ),
        remote_cache_dir: str = ".cache/covalent",
        python3_path: str = "",
        run_local_on_ssh_fail: bool = False,
        **kwargs,
    ) -> None:

        self.username = username
        self.hostname = hostname
        self.ssh_key_file = ssh_key_file
        self.cache_dir = cache_dir
        self.remote_cache_dir = remote_cache_dir

        self.python3_path = python3_path
        self.run_local_on_ssh_fail = run_local_on_ssh_fail
        self.channel = None

        # Write executor-specific parameters to the configuration file, if they were missing:
        self._update_params()

        base_kwargs = {"cache_dir": self.cache_dir}
        for key in kwargs:
            if key in [
                "conda_env",
                "current_env_on_conda_fail",
            ]:
                base_kwargs[key] = kwargs[key]

        super().__init__(**base_kwargs)

    async def execute(self, function: Callable, args: List, kwargs: Dict, dispatch_id: str, results_dir: str, node_id: int = -1) -> Any:
        """
        Set the local variables if needed and execute the `run()` function. This also takes care
        of redirecting the stdout and stderr to their respective locations.

        Args:
            function: Function to be sent to `run`.
            args: Postional arguments of above function.
            kwargs: Keyword arguments of above function.
            dispatch_id: Dispatch ID of this workflow.
            results_dir: Results directory for this workflow.
            node_id: Node ID of this electron/node.
        
        Returns:
            An awaitable coroutine which once awaited will return a tuple containing:
                result: Result of the function execution.
                stdout: Any print statements to stdout.
                stderr: Any prints to stderr.
        """

        self.dispatch_id = dispatch_id
        self.node_id = node_id
        return await super().execute(function, args, kwargs, dispatch_id, results_dir, node_id)

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
        remote_function_file = os.path.join(
            self.remote_cache_dir, f"function_{operation_id}.pkl"
        )

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

        return function_file, script_file, remote_function_file, remote_script_file, remote_result_file

    def _update_params(self) -> None:
        """
        Helper function for setting configuration values, if they were missing from the
            configuration file.

        Args:
            None

        Returns:
            None
        """

        params = {"executors": {"ssh": {}}}
        params["executors"]["ssh"]["username"] = self.username
        params["executors"]["ssh"]["hostname"] = self.hostname
        if self.ssh_key_file != "":
            params["executors"]["ssh"]["ssh_key_file"] = self.ssh_key_file
        if self.python3_path != "":
            params["executors"]["ssh"]["python3_path"] = self.python3_path

        update_config(params, override_existing=False)

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

            result = None

            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                raise e

            return result
        else:
            app_log.error(message)
            print(f"{message}", file=sys.stderr)
            raise RuntimeError

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
                conn = await asyncssh.connect(self.hostname,
                                                   username=self.username,
                                                   client_keys=[self.ssh_key_file],
                                                   known_hosts=None)

                ssh_success = True
            except (socket.gaierror, ValueError, TimeoutError) as e:
                app_log.error(e)


        else:
            message = "no SSH key file found. Cannot connect to host."
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

    async def run(self, function: Callable, args: list, kwargs: dict) -> Coroutine:
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

        operation_id = f"{self.dispatch_id}_{self.node_id}"

        exception = None

        ssh_success, conn = await self._client_connect()

        if not ssh_success:
            message = f"Could not connect to host '{self.hostname}' as user '{self.username}'"
            return self._on_ssh_fail(function, args, kwargs, message)

        message = f"Executing node {self.node_id} on host {self.hostname}."
        app_log.debug(message)

        if self.python3_path == "":
            cmd = "which python3"
            # client_in, client_out, client_err = self.client.exec_command(cmd)
            result = await conn.run(cmd)
            client_out = result.stdout
            client_err = result.stderr
            # self.python3_path = client_out.read().decode("utf8").strip()
            self.python3_path = client_out.strip()

        if self.python3_path == "":
            message = f"No Python 3 installation found on host machine {self.hostname}"
            return self._on_ssh_fail(function, args, kwargs, message)

        cmd = f"mkdir -p {self.remote_cache_dir}"

        result = await conn.run(cmd)
        client_out = result.stdout
        client_err = result.stderr

        err = client_err
        if err != "":
            app_log.warning(err)

        # Pickle and save location of the function and its arguments:
        function_file, script_file, remote_function_file, remote_script_file, remote_result_file = self._write_function_files(operation_id, function, args, kwargs)

        await asyncssh.scp(function_file, (conn, remote_function_file))
        await asyncssh.scp(script_file, (conn, remote_script_file))

        # Run the function:
        cmd = f"{self.python3_path} {remote_script_file}"
        result = await conn.run(cmd)
        err = result.stderr.strip()
        if err != "":
            app_log.warning(err)

        # Check that a result file was produced:
        cmd = f"ls {remote_result_file}"
        result = await conn.run(cmd)
        client_out = result.stdout
        if client_out.strip() != remote_result_file:
            message = f"Result file {remote_result_file} on remote host {self.hostname} was not found"
            return self._on_ssh_fail(function, args, kwargs, message)

        # scp the pickled result to the local machine here:
        result_file = os.path.join(self.cache_dir, f"result_{operation_id}.pkl")
        await asyncssh.scp((conn, remote_result_file), result_file)

        # Load the result file:
        with open(result_file, "rb") as f_in:
            result, exception = pickle.load(f_in)

        if exception is not None:
            app_log.debug(f"exception: {exception}")
            raise exception

        await conn.wait_closed()
        return result

