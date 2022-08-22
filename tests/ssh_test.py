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


import os
from unittest.mock import AsyncMock, mock_open, patch

import pytest

from covalent_ssh_plugin import SSHExecutor


def test_init(tmp_path):
    """Test that initialization properly sets member variables."""

    key_path = tmp_path / "key_file"
    key_path.touch()

    cache_dir = tmp_path / "cache_dir"

    _config_data = {
        "dispatcher.cache_dir": str(cache_dir),
        "executors.ssh.user": "centos",
        "executors.ssh.hostname": "12.12.12.12",
        "executors.ssh.ssh_key_file": "~/.ssh/id_rsa",
        "executors.ssh.remote_cache_dir": "/home/centos",
        "executors.ssh.python_path": "python3.8",
        "executors.ssh.conda_env": "py-3.8",
    }

    def get_config_mock(key):
        return _config_data[key]

    with patch("covalent._shared_files.config._config_manager") as _config_manager_mock:
        _config_manager_mock.config_data = _config_data
        _config_manager_mock.get.side_effect = get_config_mock

        executor = SSHExecutor(
            username="user",
            hostname="host",
            ssh_key_file=str(key_path),
        )

        assert executor.username == "user"
        assert executor.hostname == "host"
        assert executor.ssh_key_file == str(key_path)
        assert executor.cache_dir == _config_data["dispatcher.cache_dir"]
        assert executor.remote_cache_dir == _config_data["executors.ssh.remote_cache_dir"]
        assert executor.python_path == _config_data["executors.ssh.python_path"]
        assert executor.run_local_on_ssh_fail is False
        assert executor.do_cleanup is True


@pytest.mark.asyncio
async def test_on_ssh_fail():
    """Test that the process runs locally upon connection errors."""

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

    executor = SSHExecutor(
        username="user",
        hostname="host",
        ssh_key_file="non-existant_key",
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


def test_file_writes():
    """Test that files get written to the correct locations."""

    executor = SSHExecutor(
        username="user",
        hostname="host",
        ssh_key_file="key_file",
    )

    def simple_task(x):
        return x

    operation_id = "dispatchid_taskid"

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
    assert remote_script_file == os.path.join(executor.remote_cache_dir, f"exec_{operation_id}.py")
    assert function_file == os.path.join(executor.cache_dir, f"function_{operation_id}.pkl")
    assert remote_function_file == os.path.join(
        executor.remote_cache_dir, f"function_{operation_id}.pkl"
    )
    assert remote_result_file == os.path.join(
        executor.remote_cache_dir, f"result_{operation_id}.pkl"
    )
