# Copyright (c) 2009-2016 The Regents of the University of Michigan
# This file is part of the HOOMD-blue project, released under the BSD 3-Clause License.

R""" Metal pair potentials.
"""

from hoomd.md import force;
from hoomd.md import nlist as nl # to avoid naming conflicts
import hoomd;
from hoomd import _hoomd
from hoomd.md import _md
from hoomd.metal import _metal

import math;
import sys;

class eam(force._force):
    R""" EAM pair potential.

    Args:
        file (str): File name with potential tables in Alloy or FS format
        type (str): Type of file potential ('Alloy', 'FS')
        nlist (:py:mod:`hoomd.md.nlist`): Neighbor list (default of None automatically creates a global cell-list based neighbor list)

    :py:class:`eam` specifies that a EAM (embedded atom method) pair potential should be applied between every
    non-excluded particle pair in the simulation.

    No coefficients need to be set for :py:class:`eam`. All specifications, including the cutoff radius, form of the
    potential, etc. are read in from the specified file.

    Particle type names must match those referenced in the EAM potential file.
    
    Particle mass (in atomic mass) **must** be set in the input script, users are allowed to set different mass values 
    other than those in the potential file.

    Two file formats are supported: *Alloy* and *FS*. They are described in LAMMPS documentation
    (commands eam/alloy and eam/fs) here: http://lammps.sandia.gov/doc/pair_eam.html
    and are also described here: http://enpub.fulton.asu.edu/cms/potentials/submain/format.htm

    .. attention::
        EAM is **NOT** supported in MPI parallel simulations.

    .. danger::
        HOOMD-blue's EAM implementation was known to be broken, the current implementation is fixed on 05/01/2017.

    Example::

        nl = nlist.cell()
        eam = pair.eam(file='name.eam.fs', type='FS', nlist=nl)
        eam = pair.eam(file='name.eam.alloy', type='Alloy', nlist=nl)

    """
    def __init__(self, file, type, nlist):
        c = hoomd.cite.article(cite_key = 'lin2017',
                         author=['L Yang','A Trevesset'],
                         title = 'Implementation of EAM and FS potentials in HOOMD-blue',
                         journal = 'Computer Physics Communications',
                         volume = 0,
                         number = 0,
                         pages = '0--0',
                         year = '2017',
                         doi = '0',
                         feature = 'EAM')
        hoomd.cite._ensure_global_bib().add(c)

        hoomd.util.print_status_line();

        # Error out in MPI simulations
        if (_hoomd.is_MPI_available()):
            if hoomd.context.current.system_definition.getParticleData().getDomainDecomposition():
                hoomd.context.msg.error("pair.eam is not supported in multi-processor simulations.\n\n")
                raise RuntimeError("Error setting up pair potential.")

        # initialize the base class
        force._force.__init__(self);
        # Translate type
        if(type == 'Alloy'): type_of_file = 0;
        elif(type == 'FS'): type_of_file = 1;
        else: raise RuntimeError('Unknown EAM input file type');

        # create the c++ mirror class
        if not hoomd.context.exec_conf.isCUDAEnabled():
            self.cpp_force = _metal.EAMForceCompute(hoomd.context.current.system_definition, file, type_of_file);
        else:
            self.cpp_force = _metal.EAMForceComputeGPU(hoomd.context.current.system_definition, file, type_of_file);

        #After load EAMForceCompute we know r_cut from EAM potential`s file. We need update neighbor list.
        self.r_cut_new = self.cpp_force.get_r_cut();
        self.nlist = nlist
        self.nlist.subscribe(lambda : self.get_rcut())
        self.nlist.update_rcut()

        #Load neighbor list to compute.
        self.cpp_force.set_neighbor_list(self.nlist.cpp_nlist);
        if hoomd.context.exec_conf.isCUDAEnabled():
            self.nlist.cpp_nlist.setStorageMode(_md.NeighborList.storageMode.full);

        hoomd.context.msg.notice(2, "Set r_cut = " + str(self.r_cut_new) + " from potential`s file '" +  str(file) + "'.\n");

        hoomd.context.current.system.addCompute(self.cpp_force, self.force_name);
        self.pair_coeff = hoomd.md.pair.coeff();

    def get_rcut(self):
        # go through the list of only the active particle types in the simulation
        ntypes = hoomd.context.current.system_definition.getParticleData().getNTypes()
        type_list = []
        for i in range(0, ntypes):
            type_list.append(hoomd.context.current.system_definition.getParticleData().getNameByType(i))
        # update the rcut by pair type
        r_cut_dict = nl.rcut()
        for i in range(0, ntypes):
            for j in range(i, ntypes):
                # get the r_cut value
                r_cut_dict.set_pair(type_list[i], type_list[j], self.r_cut_new)
        return r_cut_dict

    def update_coeffs(self):
        # check that the pair coefficients are valid
        pass;
