import numpy as np
import dctkit
from dctkit.mesh import util
from dctkit.math import circumcenter as circ
import os

cwd = os.path.dirname(__file__)


def test_circumcenter(setup_test):

    filename = "data/test1.msh"
    full_path = os.path.join(cwd, filename)
    numNodes, numElements, S_2, node_coord, _ = util.read_mesh(full_path)

    print(f"The number of nodes in the mesh is {numNodes}")
    print(f"The number of faces in the mesh is {numElements}")
    print(f"The vectorization of the face matrix is \n {S_2}")
    print(f"The coordinates of the nodes are \n {node_coord}")

    circ_true = np.empty((numElements, S_2.shape[1]), dtype=dctkit.float_dtype)
    circ_true[0, :] = np.array([0.5, 0, 0], dtype=dctkit.float_dtype)
    circ_true[1, :] = np.array([1, 0.5, 0], dtype=dctkit.float_dtype)
    circ_true[2, :] = np.array([0, 0.5, 0], dtype=dctkit.float_dtype)
    circ_true[3, :] = np.array([0.5, 1, 0], dtype=dctkit.float_dtype)
    for i in range(numElements):
        circ_i = circ.circumcenter(S_2[i, :], node_coord)[0]
        assert circ_i.dtype == dctkit.float_dtype
        assert np.allclose(circ_i, circ_true[i, :])
