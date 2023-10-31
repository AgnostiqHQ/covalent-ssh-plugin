"""
Load task `fn` from pickle. Run it. Save the result.
"""
import os
import sys
from pathlib import Path

result = None
exception = None

# NOTE: Paths must be substituted-in here by the executor.
remote_result_file = Path("{remote_result_file}").resolve()
remote_function_file = Path("{remote_function_file}").resolve()
current_remote_workdir = Path("{current_remote_workdir}").resolve()

try:
    # Make sure cloudpickle is available.
    import cloudpickle as pickle
except Exception as e:
    import pickle

    with open(remote_result_file, "wb") as f_out:
        pickle.dump((None, e), f_out)
        sys.exit(1)  # Error.

current_dir = os.getcwd()

# Read the function object and arguments from pickle file.
with open(remote_function_file, "rb") as f_in:
    fn, args, kwargs = pickle.load(f_in)

try:
    # Execute the task `fn` inside the remote workdir.
    current_remote_workdir.mkdir(parents=True, exist_ok=True)
    os.chdir(current_remote_workdir)

    result = fn(*args, **kwargs)

except Exception as e:
    exception = e
finally:
    os.chdir(current_dir)

# Save the result to pickle file.
with open(remote_result_file, "wb") as f_out:
    pickle.dump((result, exception), f_out)
