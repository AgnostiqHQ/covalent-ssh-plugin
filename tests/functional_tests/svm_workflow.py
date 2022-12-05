import covalent as ct
import pytest
from numpy.random import permutation
from sklearn import datasets, svm

from tests.functional_tests.fixtures.executor import executor

deps_pip = ct.DepsPip(packages=["numpy==1.23.2", "scikit-learn==1.1.2"])


@pytest.mark.functional_tests
def test_svm_workflow():
    @ct.electron
    def load_data():
        iris = datasets.load_iris()
        perm = permutation(iris.target.size)
        iris.data = iris.data[perm]
        iris.target = iris.target[perm]
        return iris.data, iris.target

    @ct.electron(executor=executor, deps_pip=deps_pip)
    def train_svm(data, C, gamma):
        X, y = data
        clf = svm.SVC(C=C, gamma=gamma)
        clf.fit(X[90:], y[90:])
        return clf

    @ct.electron
    def score_svm(data, clf):
        X_test, y_test = data
        return clf.score(X_test[:90], y_test[:90])

    @ct.lattice
    def run_experiment(C=1.0, gamma=0.7):
        data = load_data()
        clf = train_svm(data=data, C=C, gamma=gamma)
        score = score_svm(data=data, clf=clf)
        return score

    dispatchable_func = ct.dispatch(run_experiment)

    dispatch_id = dispatchable_func(C=1.0, gamma=0.7)
    result = ct.get_result(dispatch_id=dispatch_id, wait=True)
    status = str(result.status)

    print(result)

    assert status == str(ct.status.COMPLETED)
