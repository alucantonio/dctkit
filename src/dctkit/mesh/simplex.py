import numpy as np
from dctkit.math import circumcenter as circ
from dctkit.math import volume


class SimplicialComplex:
    """Simplicial complex class.

    Args:
        tet_node_tags (int32 np.array): (num_tet x num_nodes_per_tet) matrix
        containing the IDs of the nodes belonging to each tetrahedron (or higher
        level simplex).
        node_coord (float np.array): coordinates of all the nodes of the cell complex.
    Attributes:
        node_coord (float np.array): coordinates of all the nodes of the cell complex.
        dim (int32): dimension of the complex
        S_p (list): list in which any entry p is the matrix containing the
                    IDs of the nodes belonging to each p-simplex.
        circ (list): list in which any entry p is a matrix containing all the
                     circumcenters of all the p-simplexes.
        boundary(list): list of the boundary operators.
    """

    def __init__(self, tet_node_tags, node_coord):
        self.node_coord = node_coord
        self.dim = tet_node_tags.shape[1] - 1
        # S_p is the matrix containing the IDs of the nodes belonging
        # to each p-dimensional simplices
        self.S_p = [None]*(self.dim + 1)
        self.S_p[-1] = tet_node_tags
        self.embedded_dim = node_coord.shape[1]
        self.boundary = [None]*self.dim
        self.circ = [None]*(self.dim)
        self.primal_volumes = [None]*(self.dim)
        # populate boundary operators
        self.get_boundary()
        # populate circ
        self.get_circumcenters()
        # populate primal volumes
        self.get_primal_volumes()

    def get_boundary(self):
        """Compute all the COO representations of the boundary matrices.
        """
        for p in range(self.dim):
            current_boundary, vals = compute_boundary_COO(self.S_p[self.dim - p])
            # FIXME: the p-dim boundary matrix is the p-1 entry of boundary[]
            self.boundary[self.dim - p - 1] = current_boundary
            self.S_p[self.dim - p - 1] = vals

    def get_circumcenters(self):
        """Compute all the circumcenters.
        """
        for p in range(self.dim):
            S_p = self.S_p[p+1]
            C = np.empty((S_p.shape[0], self.node_coord.shape[1]))
            for i in range(S_p.shape[0]):
                C[i, :] = circ.circumcenter(S_p[i, :], self.node_coord)
            self.circ[p] = C

    def get_primal_volumes(self):
        """Compute all the primal volumes.
        """
        unsigned_range = self.dim
        if self.dim == self.embedded_dim:
            unsigned_range -= 1
        for p in range(unsigned_range):
            S = self.S_p[p+1]
            rows, _ = S.shape
            primal_volumes = np.empty(rows)
            for i in range(rows):
                primal_volumes[i] = volume.unsigned_volume(S[i, :], self.node_coord)
            self.primal_volumes[p] = primal_volumes
        if self.dim == self.embedded_dim:
            S_p = self.S_p[self.dim]
            rows, _ = S_p.shape
            primal_volumes = np.empty(rows)
            for i in range(rows):
                primal_volumes[i] = volume.signed_volume(S_p[i, :], self.node_coord)
            self.primal_volumes[self.dim-1] = primal_volumes


def simplex_array_parity(s):
    """Compute the number of transpositions needed to sort the array
       in ascending order modulo 2.

       (Copied from PyDEC, dec/simplex_array.py)

        Args:
            s (np.array): array of the simplices.

        Returns:
            trans (np.array): array of the transpositions needed modulo 2.

    """
    s = s.copy()
    M, N = s.shape

    # number of transpositions used to sort the
    # indices of each simplex (row of s)
    trans = np.zeros_like(s[:, 0])
    seq = np.arange(M)

    # count the transpositions
    for i in range(N - 1):
        pos = s.argmin(axis=1)
        s[seq, pos] = s[:, 0]
        pos.clip(0, 1, pos)
        trans = trans + pos
        s = s[:, 1:]

    # compute parity
    trans %= 2

    return trans


def compute_face_to_edge_connectivity(S_2):
    """Compute node-to-edge matrix, edge-to-face matrix and orientations
       of the edges with respect to faces.

    Args:
        nodeTagsPerElem (np.array): 1-dimensional array of node tags.

    Returns:
        C (np.array): (num_faces x edges_per_face) matrix encoding the
                        relative orientation of each edge (columns) with
                        respect to a parent face (rows).
        NtE (np.array): matrix containing the IDs of the nodes (columns)
                        belonging to each edge (rows) of the mesh.
        EtF (np.array): matrix containing the IDs of the edges (columns)
                        belonging to each face (rows) of the mesh.

    """

    num_simplices = S_2.shape[0]
    faces_per_simplex = S_2.shape[1]
    num_faces = num_simplices * faces_per_simplex

    # calculate orientations
    orientations = 1 - 2 * simplex_array_parity(S_2)

    # sort S_2 lexicographically
    S_2.sort(axis=1)

    faces = np.empty((num_faces, faces_per_simplex + 1), dtype=int)
    # compute edges with their induced orientations and membership simplex
    # and store this information in faces
    for i in range(faces_per_simplex):
        rows = faces[num_simplices * i:num_simplices * (i + 1)]
        rows[:, :i] = S_2[:, :i]
        rows[:, i:-2] = S_2[:, i + 1:]
        rows[:, -1] = np.arange(num_simplices)
        rows[:, -2] = ((-1)**i) * orientations

    # order faces w.r.t the last column
    # in this way we have a different simplex
    # for any three rows of the matrix
    temp = faces[faces[:, -1].argsort()]
    edge = temp[:, :2]

    # orientation
    C = temp[:, -2].reshape(len(temp[:, :2]) // 3, 3)

    # save edges without repetitions, indexes to restore the original
    # matrix and number of occurences of any vector
    vals, idx, count = np.unique(edge,
                                 axis=0,
                                 return_index=True,
                                 return_counts=True)

    big = np.c_[vals, count, idx]

    # sort to preserve the initial order
    big = big[big[:, -1].argsort()]

    # update count and vals w.r.t the original order
    count = big[:, 2]
    vals = big[:, :2]

    # save the edge repeated
    rep_edges = vals[count > 1]

    # index position of rep_edges in the original array edge
    position = np.array(
        [np.where((edge == i).all(axis=1))[0] for i in rep_edges])
    position = np.concatenate(position)

    # create the vectors of label
    EtF = np.array(range(len(edge)))

    # eliminate duplicate labels
    EtF[position[1::2]] = position[::2]

    # build edge to face matrix
    EtF = EtF.reshape(len(edge) // 3, 3)

    # compute node to edge matrix
    NtE = faces[np.lexsort(faces[:, :-2].T[::-1])][:, :2]
    NtE = np.unique(NtE, axis=0)

    return C, NtE, EtF


def compute_boundary_COO(S_p):
    """Compute the COO representation of the boundary matrix of S_p

    Args:
        S_p (np.array): matrix of the IDs of the nodes belonging to each p-simplex.
    Returns:
        boundary_COO (tuple): tuple with the COO representation of the boundary
        vals (np.array): np.array matrix of node tags per (p-1)-face ordered
                         lexicographically
    """
    num_simplices = S_p.shape[0]
    faces_per_simplex = S_p.shape[1]
    num_faces = num_simplices * faces_per_simplex

    # compute array of relative orientations of the (p-1)-faces wrt the p-simplices
    orientations = 1 - 2 * simplex_array_parity(S_p)

    # sort the rows of S_p lexicographically
    # FIXME: avoid making a copy and sorting every time
    F = S_p.copy()
    F.sort(axis=1)

    # S_(p-1) matrix with repeated (p-1)-simplices and with two extra columns
    S_pm1_ext = np.empty((num_faces, faces_per_simplex + 1), dtype=np.int32)

    # find the node IDs of the (p-1)-simplices and store their relative
    # orientations wrt the parent simplex
    for i in range(faces_per_simplex):
        # remove the i-th column from the S_p matrix and put the result in the
        # appropriate block S_pm1_ext
        rows = S_pm1_ext[num_simplices * i:num_simplices * (i + 1)]
        rows[:, :i] = F[:, :i]
        rows[:, i:-2] = F[:, i + 1:]
        # put IDs of the p-simplices in the last column
        rows[:, -1] = np.arange(num_simplices)
        # put the orientations in the next-to-last-column
        rows[:, -2] = ((-1)**i) * orientations

    # order faces lexicographically (copied from PyDEC)
    # FIXME: maybe use sort
    faces_ordered = S_pm1_ext[np.lexsort(S_pm1_ext[:, :-2].T[::-1])]

    values = faces_ordered[:, -2]
    column_index = faces_ordered[:, -1]
    edge = faces_ordered[:, :-2]

    # compute vals and rows_index
    vals, rows_index = np.unique(edge, axis=0, return_inverse=True)
    boundary_COO = (rows_index, column_index, values)

    return boundary_COO, vals
