# Copyright 2021 Agnostiq Inc.
#
# This file is part of Covalent.
#
# Licensed under the Apache License 2.0 (the "License"). A copy of the
# License may be obtained with this software package or at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Use of this file is prohibited except in compliance with the License.
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Executor plugin for executing the function on a remote machine through SSH.
"""

import asyncio
import os
import socket
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple, Union

import asyncssh
import cloudpickle as pickle
from covalent._results_manager import Result
from covalent._shared_files import logger
from covalent._shared_files.config import get_config
from covalent.executor.executor_plugins.remote_executor import RemoteExecutor

EXECUTOR_PLUGIN_NAME = "SSHExecutor"

app_log = logger.app_log
log_stack_info = logger.log_stack_info

_EXECUTOR_PLUGIN_DEFAULTS = {
    "username": "",
    "hostname": "",
    "ssh_key_file": os.path.join(os.environ["HOME"], ".ssh/id_rsa"),
    "cache_dir": str(Path(get_config("dispatcher.cache_dir")).expanduser().resolve()),
    "python_path": "python",
    "conda_env": "",
    "remote_cache": ".cache/covalent",
    "run_local_on_ssh_fail": False,
    "remote_workdir": "covalent-workdir",
    "create_unique_workdir": False,
}


class SSHExecutor(RemoteExecutor):
    """
    Async executor class that invokes the input function on a remote server.

    Args:
        username: Username used to authenticate over SSH.
        hostname: Address or hostname of the remote server.
        ssh_key_file: Filename of the private key used for authentication with the remote server.
        cache_dir: Local cache directory used by this executor for temporary files.
        python_path: The path to the Python 3 executable on the remote server.
        conda_env: The conda env (if any) to be used on the remote server.
        remote_cache: Remote server cache directory used for temporary files.
        run_local_on_ssh_fail: If True, and the execution fails to run on the remote server,
            then the execution is run on the local machine.
        remote_workdir: The working directory on the remote server used for storing files produced from workflows.
        create_unique_workdir: Whether to create unique sub-directories for each node / task / electron.
        poll_freq: Number of seconds to wait for before retrying the result poll.
        do_cleanup: Delete all the intermediate files or not if True.
        max_connection_attempts: Maximum number of attempts to establish SSH connection.
        retry_wait_time: Time to wait (in seconds) before reattempting connection.
    """

    def __init__(
        self,
        username: str,
        hostname: str,
        ssh_key_file: str = None,
        cache_dir: str = None,
        python_path: str = "",
        conda_env: str = None,
        remote_cache: str = "",
        run_local_on_ssh_fail: bool = False,
        remote_workdir: str = "",
        create_unique_workdir: Optional[bool] = None,
        poll_freq: int = 15,
        do_cleanup: bool = True,
        retry_connect: bool = True,
        max_connection_attempts: int = 5,
        retry_wait_time: int = 5,
    ) -> None:

        remote_cache = (
            remote_cache or get_config("executors.ssh.remote_cache") or ".cache/covalent"
        )

        super().__init__(poll_freq=poll_freq, remote_cache=remote_cache)

        self.username = username or get_config("executors.ssh.username")
        self.hostname = hostname or get_config("executors.ssh.hostname")

        self.python_path = python_path or get_config("executors.ssh.python_path") or "python"
        self.conda_env = conda_env or get_config("executors.ssh.conda_env")

        self.cache_dir = cache_dir or get_config("dispatcher.cache_dir")
        self.cache_dir = str(Path(self.cache_dir).expanduser().resolve())

        self.run_local_on_ssh_fail = run_local_on_ssh_fail

        self.remote_workdir = remote_workdir or get_config("executors.ssh.remote_workdir")
        self.create_unique_workdir = (
            get_config("executors.ssh.create_unique_workdir")
            if create_unique_workdir is None
            else create_unique_workdir
        )

        self.do_cleanup = do_cleanup
        self.retry_connect = retry_connect
        self.max_connection_attempts = max_connection_attempts
        self.retry_wait_time = retry_wait_time

        ssh_key_file = ssh_key_file or get_config("executors.ssh.ssh_key_file")
        self.ssh_key_file = str(Path(ssh_key_file).expanduser().resolve())

    def _write_function_files(
        self,
        operation_id: str,
        fn: Callable,
        args: list,
        kwargs: dict,
        current_remote_workdir: str = ".",
    ) -> Tuple[str, str, str, str, str]:
        """
        Helper function to pickle the function to be executed to file, and write the
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
        remote_function_file = os.path.join(self.remote_cache, f"function_{operation_id}.pkl")
        remote_result_file = os.path.join(self.remote_cache, f"result_{operation_id}.pkl")

        # Write the code that the remote server will use to execute the function.

        message = f"Function file names:\nLocal function file: {function_file}\n"
        message += f"Remote function file: {remote_function_file}"
        app_log.debug(message)

        exec_blank = Path(__file__).parent / "exec.py"
        script_file = os.path.join(self.cache_dir, f"exec_{operation_id}.py")
        remote_script_file = os.path.join(self.remote_cache, f"exec_{operation_id}.py")

        with open(exec_blank, "r", encoding="utf-8") as f_blank:
            exec_script = f_blank.read().format(
                remote_result_file=remote_result_file,
                remote_function_file=remote_function_file,
                current_remote_workdir=current_remote_workdir,
            )
            with open(script_file, "w", encoding="utf-8") as f_out:
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

    async def _client_connect(self) -> Tuple[bool, Optional[asyncssh.SSHClientConnection]]:
        """
        Attempts connection to the remote host.

        Args:
            None

        Returns:
            True if connection to the remote host was successful, False otherwise.
        """

        ssh_success = False
        conn = None

        if not os.path.exists(self.ssh_key_file):
            message = f"SSH key file {self.ssh_key_file} does not exist."
            app_log.error(message)
            raise RuntimeError(message)

        try:
            conn = await self._attempt_client_connect()
            ssh_success = conn is not None
        except (socket.gaierror, ValueError, TimeoutError) as e:
            app_log.error(e)

        return ssh_success, conn

    async def _attempt_client_connect(self) -> Optional[asyncssh.SSHClientConnection]:
        """
        Helper function that catches specific errors and retries connecting to the remote host.

        Args:
            max_attempts: Gives up after this many attempts.

        Returns:
            An `SSHClientConnection` object if successful, None otherwise.
        """

        # Retry connecting if any of these errors happen:
        _retry_errs = (
            ConnectionRefusedError,
            OSError,  # e.g. Network unreachable
            asyncssh.ConnectionLost,  # e.g. Connection reset by remote host
        )

        address = f"{self.username}@{self.hostname}"
        attempt_max = self.max_connection_attempts

        attempt = 0
        while attempt < attempt_max:

            try:
                # Exit here if the connection is successful.
                return await asyncssh.connect(
                    self.hostname,
                    username=self.username,
                    client_keys=[self.ssh_key_file],
                    known_hosts=None,
                )
            except _retry_errs as err:

                if not self.retry_connect:
                    app_log.error(f"{err} ({address} | retry disabled).")
                    raise err

                app_log.warning(f"{err} ({address} | retry {attempt+1}/{attempt_max})")
                await asyncio.sleep(self.retry_wait_time)

            finally:
                attempt += 1

        # Failed to connect to client.
        return None

    async def cleanup(
        self,
        conn: asyncssh.SSHClientConnection,
        function_file: str,
        script_file: str,
        result_file: str,
        remote_function_file: str,
        remote_script_file: str,
        remote_result_file: str,
    ) -> None:
        """
        Perform cleanup of created files

        Args:
            conn: Connection object to connect to the remote machine
            function_file: Path to the function file to be deleted locally
            script_file: Path to the script file to be deleted locally
            result_file: Path to the result file to be deleted locally
            remote_function_file: Path to the function file to be deleted on remote
            remote_script_file: Path to the script file to be deleted on remote
            remote_result_file: Path to the result file to be deleted on remote

        Returns:
            None
        """

        os.remove(function_file)
        os.remove(script_file)
        os.remove(result_file)
        await conn.run(f"rm {remote_function_file}")
        await conn.run(f"rm {remote_script_file}")
        await conn.run(f"rm {remote_result_file}")

    async def _validate_credentials(self) -> bool:
        """
        Validates whether the credentials file exists

        Args:
            None

        Returns:
            boolean indicating if credentials file exists

        Raises:
            RuntimeError: If the file does not exist
        """

        cred_path = Path(self.ssh_key_file)
        if not cred_path.is_file():
            raise RuntimeError(f"SSH key file {self.ssh_key_file} does not exist.")

        return True

    async def _upload_task(
        self,
        conn: asyncssh.SSHClientConnection,
        function_file: str,
        remote_function_file: str,
        script_file: str,
        remote_script_file: str,
    ) -> None:
        """
        Upload the required files to the remote machine.
        In this case, it is done using SCP.

        Args:
            conn: Connection object to connect the the remote machine
            function_file: Path to the function file to be uploaded
            remote_function_file: Path where to store the uploaded function file on remote
            script_file: Path to script file to be uploaded
            remote_script_file: Path where to store the uploaded script file on remote

        Returns:
            None
        """

        await asyncssh.scp(function_file, (conn, remote_function_file))
        await asyncssh.scp(script_file, (conn, remote_script_file))

    async def submit_task(
        self, conn: asyncssh.SSHClientConnection, remote_script_file: str
    ) -> asyncssh.SSHCompletedProcess:
        """
        Submit the task for execution and return the corresponding command output.

        Args:
            conn: Connection object to connect to the remote machine
            remote_script_file: Path to the remote script file to be executed

        Returns:
            asyncssh.SSHCompletedProcess: Containing information about the executed command
        """

        cmd = f"{self.python_path} {remote_script_file}"

        if self.conda_env:
            cmd = f'eval "$(conda shell.bash hook)" && conda activate {self.conda_env} && {cmd}'

        app_log.debug(f"Running the function on remote now with command: {cmd}")
        result = await conn.run(cmd)
        app_log.debug("Function run finished")

        return result

    async def get_status(
        self, conn: asyncssh.SSHClientConnection, remote_result_file: str
    ) -> bool:
        """
        Getting the status of remote result

        Args:
            conn: Connection object for connecting to remote
            remote_result_file: Path to the result file on remote

        Returns:
            boolean indicating whether the result file exists on remote machine or not
        """

        cmd = f"ls {remote_result_file}"
        check_result_file = await conn.run(cmd)
        client_out = check_result_file.stdout

        return client_out.strip() == remote_result_file

    async def _poll_task(
        self, conn: asyncssh.SSHClientConnection, remote_result_file: str, retries: int = 5
    ) -> bool:
        """
        Poll the remote machine to check result existence after every self.poll_freq seconds

        Args:
            conn: Connection object for connecting to remote
            remote_result_file: Path to the result file on remote
            retries: Number of retries to perform before marking it as failure

        Returns:
            boolean indicating whether result file exists even after specified number of
            retries and waiting time
        """

        app_log.debug("Checking that result file was produced on remote machine...")

        while not await self.get_status(conn, remote_result_file):
            if retries == 1:
                return False
            await asyncio.sleep(self.poll_freq)
            retries -= 1

        return True

    async def query_result(
        self, conn, result_file: str, remote_result_file: str
    ) -> Tuple[Result, Exception]:
        """
        Query the result from the remote machine

        Args:
            conn: Connection object to connect to the remote machine
            result_file: Path to the result file to copy result to locally
            remote_result_file: Path to the remote result file to be copied from

        Returns:
            Result: Result object itself
            Exception: If there was any exception when executing the function
        """

        app_log.debug(f"Copying result file from remote machine to local path {result_file}...")
        await asyncssh.scp((conn, remote_result_file), result_file)

        # Load the result file:
        app_log.debug("Loading result file")
        with open(result_file, "rb") as f_in:
            result, exception = pickle.load(f_in)

        return result, exception

    async def cancel(self) -> bool:
        """
        Cancel the function execution
        """
        raise NotImplementedError("Not implemented as it is unsupported for now")

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

        if self.create_unique_workdir:
            current_remote_workdir = os.path.join(
                self.remote_workdir, dispatch_id, f"node_{node_id}"
            )
        else:
            current_remote_workdir = self.remote_workdir

        exception = None

        await self._validate_credentials()

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
            completed_proc = await conn.run(
                f'eval "$(conda shell.bash hook)" && conda env list | grep {self.conda_env}'
            )

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

        cmd = f"mkdir -p {self.remote_cache}"

        mkdir_cache = await conn.run(cmd)
        if client_err := mkdir_cache.stderr:
            app_log.warning(client_err)

        # Pickle and save location of the function and its arguments:
        (
            function_file,
            script_file,
            remote_function_file,
            remote_script_file,
            remote_result_file,
        ) = self._write_function_files(
            operation_id, function, args, kwargs, current_remote_workdir
        )

        app_log.debug("Copying function file to remote machine...")
        await self._upload_task(
            conn, function_file, remote_function_file, script_file, remote_script_file
        )

        app_log.debug("Running function file in remote machine...")
        result = await self.submit_task(conn, remote_script_file)

        if result.exit_status != 0:
            message = result.stderr.strip()
            message = message or f"Task exited with nonzero exit status {result.exit_status}."
            app_log.warning(message)
            return self._on_ssh_fail(function, args, kwargs, message)

        if not await self._poll_task(conn, remote_result_file):
            message = (
                f"Result file {remote_result_file} on remote host {self.hostname} was not found"
            )
            return self._on_ssh_fail(function, args, kwargs, message)

        # scp the pickled result to the local machine here:
        result_file = os.path.join(self.cache_dir, f"result_{operation_id}.pkl")
        result, exception = await self.query_result(conn, result_file, remote_result_file)

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
