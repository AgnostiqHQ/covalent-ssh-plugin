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
Executor plugin for executing the function on a remote machine through ssh.
"""

# Required for all executor plugins
import io
import os
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

# Executor-specific imports:
import cloudpickle as pickle
import paramiko

# Covalent imports
from covalent._shared_files import logger
from covalent._shared_files.config import get_config, update_config
from covalent._shared_files.util_classes import DispatchInfo
from covalent._workflow.transport import TransportableObject
from covalent.executor import BaseExecutor
from scp import SCPClient

# The plugin class name must be given by the executor_plugin_name attribute:
executor_plugin_name = "SSHExecutor"

app_log = logger.app_log
log_stack_info = logger.log_stack_info


class SSHExecutor(BaseExecutor):
    """
    Executor class that invokes the input function on a remote server.
    """

    def __init__(
        self,
        username: str,
        hostname: str,
        ssh_dir: str = os.environ["HOME"] + "/.ssh",
        remote_dir: str = ".cache/covalent",
        python3_path: str = "",
        run_local_on_ssh_fail: bool = False,
        *args,
        **kwargs,
    ) -> None:

        self.username = username
        self.hostname = hostname
        self.ssh_dir = ssh_dir
        self.remote_dir = remote_dir
        self.hosts = os.path.join(self.ssh_dir, "known_hosts")

        self.python3_path = python3_path
        self.run_local_on_ssh_fail = run_local_on_ssh_fail
        self.channel = None

        # Write executor-specific parameters to the configuration file, if they were missing:
        self._update_params()

        if "cache_dir" not in kwargs:
            kwargs["cache_dir"] = get_config("dispatcher.cache_dir")

        self.args = args
        self.kwargs = kwargs

        base_kwargs = {}
        for key in self.kwargs:
            if key in [
                "log_stdout",
                "log_stderr",
                "conda_env",
                "cache_dir",
                "current_env_on_conda_fail",
            ]:
                base_kwargs[key] = self.kwargs[key]

        super().__init__(**base_kwargs)

    def execute(
        self,
        function: TransportableObject,
        execution_args: dict,
        kwargs: Any,
        dispatch_id: str,
        results_dir: str,
        node_id: int = -1,
    ) -> Any:
        """
        Executes the input function and returns the result.

        Args:
            function: The input python function which will be executed and whose result
                      is ultimately returned by this function.
            kwargs: Keyword arguments to be used by function.
            execution_args: Executor-specific arguments.
            dispatch_id: The unique identifier of the external lattice process which is
                         calling this function.
            node_id: The node ID of this task in the bigger workflow graph.

        Returns:
            output: The result of the executed function.
        """

        operation_id = f"{dispatch_id}_{node_id}"

        dispatch_info = DispatchInfo(dispatch_id)
        fn = function.get_deserialized()

        # Pickle and save location of the function and its arguments:
        function_file = os.path.join(self.cache_dir, f"function_{operation_id}.pkl")
        with open(function_file, "wb") as f_out:
            pickle.dump((fn, kwargs), f_out)
        remote_function_file = os.path.join(self.remote_dir, f"function_{operation_id}.pkl")

        # Write the code that the remote server will use to execute the function.
        remote_result_file = os.path.join(self.remote_dir, f"result_{operation_id}.pkl")
        exec_script = "\n".join(
            [
                "import sys",
                "from covalent import executor" "",
                "try:",
                "    import cloudpickle as pickle",
                "except ModuleNotFoundError:",
                "    sys.exit()",
                "",
                f"with open('{remote_function_file}', 'rb') as f_in:",
                "    fn, kwargs = pickle.load(f_in)",
                "result = fn(**kwargs)",
                "",
                f"with open('{remote_result_file}','wb') as f_out:",
                "    pickle.dump(result, f_out)",
                "",
            ]
        )
        script_file = os.path.join(self.cache_dir, f"exec_{operation_id}.py")
        remote_script_file = os.path.join(self.remote_dir, f"exec_{operation_id}.py")
        with open(script_file, "w") as f_out:
            f_out.write(exec_script)

        ssh_success = self._client_connect()

        with self.get_dispatch_context(dispatch_info), redirect_stdout(
            io.StringIO()
        ) as stdout, redirect_stderr(io.StringIO()) as stderr:

            if not ssh_success:
                message = f"Could not connect to host {self.hostname} as user {self.username}"
                return self._on_ssh_fail(fn, kwargs, stdout, stderr, message)

            message = f"Executing node {node_id} on host {self.hostname}."
            app_log.debug(message)

            if self.python3_path == "":
                cmd = "which python3"
                client_in, client_out, client_err = self.client.exec_command(cmd)
                self.python3_path = client_out.read().decode("utf8").strip()
                if self.python3_path == "":
                    message = f"No Python 3 installation found on host machine {self.hostname}"
                    return self._on_ssh_fail(fn, kwargs, stdout, stderr, message)

            cmd = f"mkdir -p {self.remote_dir}"
            client_in, client_out, client_err = self.client.exec_command(cmd)
            err = client_err.read().decode("utf8")
            if err != "":
                app_log.warning(err)

            # scp pickled function and run script to server here:
            self.scp.put(function_file, remote_function_file)
            self.scp.put(script_file, remote_script_file)

            # Run the function:
            cmd = f"{self.python3_path} {remote_script_file}\n"
            cmd = f"conda activate cova && python3 {remote_script_file}"
            client_in, client_out, client_err = self.client.exec_command(cmd)
            err = client_err.read().decode("utf8").strip()
            if err != "":
                app_log.warning(err)

            # Check that a result file was produced:
            cmd = f"ls {remote_result_file}"
            client_in, client_out, client_err = self.client.exec_command(cmd)
            if client_out.read().decode("utf8").strip() != remote_result_file:
                message = f"Result file {remote_result_file} on remote host {self.hostname} was not found"
                return self._on_ssh_fail(fn, kwargs, stdout, stderr, message)

            # scp the pickled result to the local machine here:
            result_file = os.path.join(self.cache_dir, f"result_{operation_id}.pkl")
            self.scp.get(remote_result_file, result_file)

            # Load the result file:
            with open(result_file, "rb") as f_in:
                result = pickle.load(f_in)

            self.client.close()

        return (result, stdout.getvalue(), stderr.getvalue())

    # flake8: noqa: C901
    def _update_params(self) -> None:
        """
        Helper function for setting configuration values, if they were missing from the
            configuration file.

        Args:
            None

        Returns:
            None
        """
        params = {"executors": {"ssh_executor": {}}}
        try:
            get_config("executors.ssh_executor.username")
        except KeyError:
            params["executors"]["ssh_executor"]["username"] = self.username

        try:
            get_config("executors.ssh_executor.hostname")
        except KeyError:
            params["executors"]["ssh_executor"]["hostname"] = self.hostname

        try:
            get_config("executors.ssh_executor.ssh_dir")
        except KeyError:
            if self.ssh_dir != "":
                params["executors"]["ssh_executor"]["ssh_dir"] = self.ssh_dir

        try:
            get_config("executors.ssh_executor.remote_dir")
        except KeyError:
            params["executors"]["ssh_executor"]["remote_dir"] = self.remote_dir

        try:
            get_config("executors.ssh_executor.python3_path")
        except KeyError:
            if self.python3_path != "":
                params["executors"]["ssh_executor"]["python3_path"] = self.python3_path

        try:
            get_config("executors.ssh_executor.run_local_on_ssh_fail")
        except KeyError:
            params["executors"]["ssh_executor"][
                "run_local_on_ssh_fail"
            ] = self.run_local_on_ssh_fail

        if params != {"executors": {"ssh_executor": {}}}:
            update_config(params)

    def _on_ssh_fail(self, fn, kwargs, stdout, stderr, message):
        """
        Handles what happens when executing the function on the remote host fails.
        """
        if self.run_local_on_ssh_fail:
            app_log.warning(message)
            result = fn(**kwargs)
            return (result, stdout.getvalue(), stderr.getvalue())
        else:
            app_log.error(message)
            raise RuntimeError

    def _client_connect(self) -> None:
        """
        Helper function for connecting to the remote host through the paramiko module.

        Args:
            None

        Returns:
            None
        """
        self.client = paramiko.SSHClient()

        ssh_success = False
        if os.path.exists(self.hosts):
            self.client.load_host_keys(self.hosts)
            try:
                self.client.connect(
                    self.hostname,
                    username=self.username,
                )
                ssh_success = True
            except paramiko.ssh_exception.SSHException as e:
                app_log.error(e)

        else:
            message = "no 'known_hosts' file found. Cannot connect to untrusted hosts."
            app_log.error(message)

        if ssh_success:
            self.scp = SCPClient(self.client.get_transport())
        else:
            self.scp = None

        return ssh_success
