# coding=utf-8

import logging
import struct

logger = logging.getLogger(__name__)

vertexstruct = struct.Struct("1f1f1f1f1f1f1f1f1f1f")
facestruct = struct.Struct("1H1H1H")

class LsbWriter:
    def __init__(self, fp):
        # The contents of the LSB file
        self.fp = fp

    def add_subset_data(self, subsetNode, vertexdata, facedata):
        vertexcount = len(vertexdata)
        for entry in vertexdata:
            if entry is None:
                vertexcount -= 1
            else:
                self.fp.write(vertexstruct.pack(*entry[0:10]))

        assert(facedata.itemsize == 2)
        facedata.tofile(self.fp)

        subsetNode.setAttribute("MeshV", str(vertexcount))
        subsetNode.setAttribute("MeshI", str(len(facedata)))

class LsbReader:
    def __init__(self):
        self.lsbfile = None

    def set_lsb_file(self, filename):
        logger.debug("Loading lsb file: " + filename)
        self.lsbfile = open(filename, "rb")

    def read_subset_data(self, subsetNode):
        # Load mesh data from lsb file
        numvertices = 0
        numfaces = 0
    
        if subsetNode.getAttribute("MeshV") != "":
            numvertices = int(subsetNode.getAttribute("MeshV"))
        if subsetNode.getAttribute("MeshI") != "":
            numfaces = int(subsetNode.getAttribute("MeshI")) // 3
    
        logger.debug("Reading %d vertices and %d faces" % (numvertices, numfaces))
    
        # When loading the face data, note that the vertex order has to be reversed for Blender, therefore [::-1] is added after struct.unpack(…)
        return (
            [vertexstruct.unpack(self.lsbfile.read(40)) for i in range(0, numvertices)],
            [facestruct.unpack(self.lsbfile.read(6))[::-1] for i in range(0, numfaces)]
        )
