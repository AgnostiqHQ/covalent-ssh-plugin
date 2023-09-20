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

"""Tests for the SSH executor plugin."""


import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from covalent_ssh_plugin import SSHExecutor

config_data = {
    "dispatcher.cache_dir": "cache_dir",
    "executors.ssh.user": "centos",
    "executors.ssh.hostname": "12.12.12.12",
    "executors.ssh.ssh_key_file": "~/.ssh/id_rsa",
    "executors.ssh.remote_cache": "/home/centos",
    "executors.ssh.python_path": "python3.8",
    "executors.ssh.conda_env": "py-3.8",
    "executors.ssh.remote_workdir": "covalent-workdir",
    "executors.ssh.create_unique_workdir": False,
}


def get_config_mock(key):
    return config_data[key]


def test_init(mocker, tmp_path):
    """Test that initialization properly sets member variables."""

    key_path = tmp_path / "key_file"
    key_path.touch()

    mocker.patch("covalent_ssh_plugin.ssh.get_config", side_effect=get_config_mock)

    executor = SSHExecutor(
        username="user",
        hostname="host",
        ssh_key_file=str(key_path),
        create_unique_workdir=True,
    )

    assert executor.username == "user"
    assert executor.hostname == "host"
    assert executor.ssh_key_file == str(key_path)
    assert executor.remote_cache == config_data["executors.ssh.remote_cache"]
    assert executor.python_path == config_data["executors.ssh.python_path"]
    assert executor.run_local_on_ssh_fail is False
    assert executor.remote_workdir == config_data["executors.ssh.remote_workdir"]
    assert executor.create_unique_workdir is True
    assert executor.do_cleanup is True


@pytest.mark.asyncio
async def test_on_ssh_fail(mocker):
    """Test that the process runs locally upon connection errors."""

    mocker.patch("covalent_ssh_plugin.ssh.get_config", side_effect=get_config_mock)

    executor = SSHExecutor(
        username="user",
        hostname="host",
        ssh_key_file="key_file",
        run_local_on_ssh_fail=True,
    )

    def simple_task(x):
        return x**2

    executor.node_id = (0,)
    executor.dispatch_id = (0,)
    mocker.patch("covalent_ssh_plugin.SSHExecutor._validate_credentials", return_value=True)
    result = await executor.run(
        function=simple_task,
        args=[5],
        kwargs={},
        task_metadata={"dispatch_id": -1, "node_id": -1},
    )
    assert result == 25

    executor.run_local_on_ssh_fail = False
    with pytest.raises(RuntimeError):
        result = await executor.run(
            function=simple_task,
            args=[5],
            kwargs={},
            task_metadata={"dispatch_id": -1, "node_id": -1},
        )


@pytest.mark.asyncio
async def test_client_connect(mocker):
    """Test that connection will fail if credentials are not supplied."""

    mocker.patch("covalent_ssh_plugin.ssh.get_config", side_effect=get_config_mock)

    executor = SSHExecutor(
        username="user",
        hostname="host",
        ssh_key_file="non-existent_key",
    )

    connected, _ = await executor._client_connect()
    assert connected is False

    # Patch to fake existence of valid SSH keyfile. Connection should still fail due to
    # the invalide username/hostname.
    mocker.patch("builtins.open", mock_open(read_data="data"))
    connected, _ = await executor._client_connect()
    assert connected is False

    # Patch to make call to paramiko.SSHClient.connect not fail with incorrect user/host/keyfile.
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("asyncssh.connect", AsyncMock())
    connected, _ = await executor._client_connect()
    assert connected is True


@pytest.mark.asyncio
async def test_current_remote_workdir(mocker):
    async def mock_conn_run(x):
        ret = MagicMock()
        ret.stdout = "3"
        ret.stderr = None
        return ret

    async def mock_wait_closed():
        return True

    mock_conn = mocker.patch("asyncssh.SSHClientConnection")
    mock_conn.run.side_effect = mock_conn_run
    mock_conn.wait_closed.side_effect = mock_wait_closed
    mocker.patch(
        "covalent_ssh_plugin.ssh.SSHExecutor._client_connect", return_value=(True, mock_conn)
    )

    async def mock_submit_task(mock_conn, file):
        ret = MagicMock()
        ret.stderr = ""
        return ret

    mocker.patch("covalent_ssh_plugin.ssh.get_config", side_effect=get_config_mock)
    mocker.patch("covalent_ssh_plugin.ssh.SSHExecutor._validate_credentials", return_value=True)
    mocker.patch("covalent_ssh_plugin.ssh.SSHExecutor._upload_task")
    mocker.patch("covalent_ssh_plugin.ssh.SSHExecutor.submit_task", side_effect=mock_submit_task)
    mocker.patch("covalent_ssh_plugin.ssh.SSHExecutor._poll_task", return_value=True)
    mocker.patch("covalent_ssh_plugin.ssh.SSHExecutor.query_result", return_value=(5, None))

    with tempfile.TemporaryDirectory() as tmp_dir:
        executor = SSHExecutor(
            username="user",
            hostname="host",
            ssh_key_file="key_file",
            remote_workdir=tmp_dir,
            create_unique_workdir=True,
            do_cleanup=False,
        )

        executor.conda_env = None

    def simple_task(x):
        return x

    dispatch_id = "asdf"
    node_id = 1
    operation_id = f"{dispatch_id}_{node_id}"
    expected_current_remote_workdir = os.path.join(tmp_dir, dispatch_id, f"node_{node_id}")

    mock__write_function_files = mocker.patch.object(SSHExecutor, "_write_function_files")
    mock__write_function_files.return_value = ("a", "b", "c", "d", "e")
    await executor.run(simple_task, [5], {}, {"dispatch_id": dispatch_id, "node_id": node_id})
    mock__write_function_files.assert_called_with(
        operation_id, simple_task, [5], {}, expected_current_remote_workdir
    )


def test_file_writes(mocker):
    """Test that files get written to the correct locations."""

    mocker.patch("covalent_ssh_plugin.ssh.get_config", side_effect=get_config_mock)

    executor = SSHExecutor(
        username="user",
        hostname="host",
        ssh_key_file="key_file",
    )

    def simple_task(x):
        return x

    dispatch_id = "dispatchid"
    task_id = "taskid"
    operation_id = f"{dispatch_id}_{task_id}"

    @patch("builtins.open", new_callable=mock_open())
    def write_files(mock):
        return executor._write_function_files(
            operation_id,
            simple_task,
            [5],
            {},
        )

    (
        function_file,
        script_file,
        remote_function_file,
        remote_script_file,
        remote_result_file,
    ) = write_files()

    assert script_file == os.path.join(executor.cache_dir, f"exec_{operation_id}.py")
    assert remote_script_file == os.path.join(executor.remote_cache, f"exec_{operation_id}.py")
    assert function_file == os.path.join(executor.cache_dir, f"function_{operation_id}.pkl")
    assert remote_function_file == os.path.join(
        executor.remote_cache, f"function_{operation_id}.pkl"
    )
    assert remote_result_file == os.path.join(executor.remote_cache, f"result_{operation_id}.pkl")
