import sys

import covalent as ct

from .executor import executor

# Basic Workflow


@ct.electron(executor=executor)
def join_words(a, b):
    return ", ".join([a, b])


@ct.electron
def excitement(a):
    return f"{a}!"


@ct.lattice
def basic_workflow(a, b):
    phrase = join_words(a, b)
    return excitement(phrase)


# Dispatch the workflow
dispatch_id = ct.dispatch(basic_workflow)("Hello", "World")
result = ct.get_result(dispatch_id=dispatch_id, wait=True)
status = str(result.status)

print(result)

if status == str(ct.status.FAILED):
    print("Basic Workflow failed to run.")
    sys.exit(1)
