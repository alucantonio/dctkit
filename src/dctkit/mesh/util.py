import gmsh
import numpy as np


def read_mesh(filename, format="gmsh"):
    """Reads mesh from file.
    Args:
        filename: name of the file containing the mesh
    Returns
        numNodes: number of mesh points.
    """
    if format != "gmsh":
        print("Mesh format NOT IMPLEMENTED!")

    gmsh.initialize()
    gmsh.open(filename)

    # Get nodes and corresponding coordinates
    nodeTags, coords, paramCoords = gmsh.model.mesh.getNodes()

    numNodes = len(nodeTags)
    # print("# nodes = ", numNodes)

    # Get 2D elements and associated node tags
    # NOTE: ONLY GET TRIANGLES
    elemTags, nodeTagsPerElem = gmsh.model.mesh.getElementsByType(2)

    # Decrease element IDs by 1 to have node indices starting from 0
    nodeTagsPerElem = np.array(nodeTagsPerElem) - 1
    nodeTagsPerElem = nodeTagsPerElem.reshape(len(nodeTagsPerElem) // 3, 3)
    # Get number of TRIANGLES
    numElements = len(elemTags)
    # print("# elements = ", numElements)

    # physicalGrps = gmsh.model.getPhysicalGroups()
    # print("physical groups: ", physicalGrps)

    # edgeNodesTags = gmsh.model.mesh.getElementEdgeNodes(2)
    # print("edge nodes tags: ", edgeNodesTags)

    # Position vectors of mesh points
    x = np.zeros((3, numNodes))

    # Loop over nodes
    for i in range(numNodes):
        # Populate tensor of node positions
        x[:, i] = coords[3 * i:3 * (i + 1)]

    x = x.T

    return numNodes, numElements, nodeTagsPerElem, x
