import covalent as ct
import pytest

# Basic Workflow


@pytest.mark.functional_tests
def test_basic_workflow():
    @ct.electron(executor="ssh")
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

    assert status == str(ct.status.COMPLETED)
