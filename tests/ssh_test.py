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

"""Tests for the SSH executor plugin."""

from multiprocessing import Queue as MPQ
import os
from unittest.mock import patch, mock_open
import pytest

import pytest

import covalent as ct
from covalent._workflow.transport import TransportableObject
from covalent.executor import SSHExecutor
from covalent._shared_files.config import get_config, update_config

def test_init():
    """Test that initialization properly sets member variables."""

    executor = SSHExecutor(
        username = "user",
        hostname = "host",
    )

    assert executor.username == "user"
    assert executor.hostname == "host"
    assert executor.ssh_key_file == os.path.join(os.environ["HOME"], ".ssh/id_rsa")
    assert executor.cache_dir == os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ["HOME"], ".cache"),
            "covalent",
        )
    assert executor.remote_cache_dir == ".cache/covalent"
    assert executor.python3_path == ""
    assert executor.run_local_on_ssh_fail == False
    assert executor.conda_env == ""
    assert executor.current_env_on_conda_fail == False

def test_update_params():
    """Test that the executor configuration parameters are properly updated."""
    
    executor = SSHExecutor(
        username = "user",
        hostname = "host",
    )

    params = get_config()["executors"]["ssh"]

    assert params["username"] == executor.username == "user"
    assert params["hostname"] == executor.hostname == "host"
    assert params["ssh_key_file"] == executor.ssh_key_file
    assert params["python3_path"] == executor.python3_path

def test_on_ssh_fail():
    """Test that the process runs locally upon connection errors."""
    
    executor = SSHExecutor(
        username = "user",
        hostname = "host",
        run_local_on_ssh_fail = True,
    )

    def simple_task(x):
        return x ** 2

    transport_function = TransportableObject(simple_task)

    result, _, _ = executor.execute(
        function = transport_function,
        args = [5],
        kwargs = {},
        info_queue = MPQ(),
        node_id = 0,
        dispatch_id = 0,
        results_dir = "./",
    )
    assert result == 25

    executor.run_local_on_ssh_fail = False
    with pytest.raises(RuntimeError):
        result, _, _  = executor.execute(
            function = transport_function,
            args = [5],
            kwargs = {},
            info_queue = MPQ(),
            node_id = 0,
            dispatch_id = 0,
            results_dir = "./",
        )

def test_client_connect(mocker):
    """Test that connection will fail if credentials are not supplied."""
    
    executor = SSHExecutor(
        username = "user",
        hostname = "host",
        ssh_key_file = "non-existant_key",
    )

    connected = executor._client_connect()
    assert connected is False

    # Patch to fake existence of valid SSH keyfile. Connection should still fail due to
    # the invalide username/hostname.
    mocker.patch("os.path.exists", return_value = True)
    connected = executor._client_connect()
    assert connected is False

    # Patch to make call to paramiko.SSHClient.connect not fail with incorrect user/host/keyfile.
    mocker.patch("paramiko.SSHClient.connect", return_value = None)
    connected = executor._client_connect()
    assert connected is True

def test_deserialization(mocker):
    """Test that the input function is deserialized."""

    executor = SSHExecutor(
        username = "user",
        hostname = "host",
    )

    def simple_task(x):
        return x

    transport_function = TransportableObject(simple_task)
    deserizlized_mock = mocker.patch.object(
        transport_function,
        "get_deserialized",
        return_value = simple_task,
    )

    with pytest.raises(RuntimeError):
        executor.execute(
            function = transport_function,
            args = [5],
            kwargs = {},
            info_queue = MPQ(),
            node_id = 0,
            dispatch_id = 0,
            results_dir = "./",
        )

    deserizlized_mock.assert_called_once()


def test_file_writes():
    """Test that files get written to the correct locations."""
    
    executor = SSHExecutor(
        username = "user",
        hostname = "host",
    )

    def simple_task(x):
        return x
    
    operation_id = "dispatchid_taskid"

    @patch("builtins.open", new_callable=mock_open())
    def write_files(mock):
        executor._write_function_files(
            operation_id,
            simple_task,
            [5],
            {},
        )

    write_files()

    assert executor.script_file == os.path.join(executor.cache_dir, f"exec_{operation_id}.py")
    assert executor.remote_script_file == os.path.join(
        executor.remote_cache_dir,
        f"exec_{operation_id}.py"
    )
    assert executor.function_file == os.path.join(
        executor.cache_dir,
        f"function_{operation_id}.pkl"
    )
    assert executor.remote_function_file == os.path.join(
        executor.remote_cache_dir,
        f"function_{operation_id}.pkl"
    )
    assert executor.remote_result_file == os.path.join(
        executor.remote_cache_dir,
        f"result_{operation_id}.pkl"
    )
