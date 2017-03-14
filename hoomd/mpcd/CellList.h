// Copyright (c) 2009-2017 The Regents of the University of Michigan
// This file is part of the HOOMD-blue project, released under the BSD 3-Clause License.

// Maintainer: mphoward

/*!
 * \file mpcd/CellList.h
 * \brief Declaration of mpcd::CellList
 */

#ifndef MPCD_CELL_LIST_H_
#define MPCD_CELL_LIST_H_

#ifdef NVCC
#error This header cannot be compiled by nvcc
#endif

#include "ParticleData.h"
#include "CommunicatorUtilities.h"

#include "hoomd/Compute.h"
#include "hoomd/GPUFlags.h"
#include "hoomd/ParticleGroup.h"

// pybind11
#include "hoomd/extern/pybind/include/pybind11/pybind11.h"

#include <array>

namespace mpcd
{
// forward declaration
class Communicator;

//! Computes the MPCD cell list on the CPU
class CellList : public Compute
    {
    public:
        //! Constructor
        CellList(std::shared_ptr<SystemDefinition> sysdef,
                 std::shared_ptr<mpcd::ParticleData> mpcd_pdata);

        //! Destructor
        virtual ~CellList();

        //! Build the cell list
        virtual void compute(unsigned int timestep);

        //! Sizes the cell list based on the box
        void computeDimensions();

        //! Get the cell list data
        const GPUArray<unsigned int>& getCellList() const
            {
            return m_cell_list;
            }

        //! Get the number of particles per cell
        const GPUArray<unsigned int>& getCellSizeArray() const
            {
            return m_cell_np;
            }

        //! Get the total number of cells in the list
        const unsigned int getNCells() const
            {
            return m_cell_indexer.getNumElements();
            }

        //! Get the cell indexer
        const Index3D& getCellIndexer() const
            {
            return m_cell_indexer;
            }

        //! Get the cell list indexer
        const Index2D& getCellListIndexer() const
            {
            return m_cell_list_indexer;
            }

        //! Get the number of cells in each dimension
        const uint3& getDim() const
            {
            return m_cell_dim;
            }

        const int3& getOriginIndex() const
            {
            return m_origin_idx;
            }

        //! Obtain the local cell index corresponding to a global cell
        const int3 getLocalCell(const int3& global) const;

        //! Obtain the global cell corresponding to local cell
        const int3 getGlobalCell(const int3& local) const;

        //! Wrap a cell into a global cell
        const int3 wrapGlobalCell(const int3& cell) const;

        //! Get the maximum number of particles in a cell
        const unsigned int getNmax() const
            {
            return m_cell_np_max;
            }

        //! Set the MPCD cell size
        /*!
         * \param cell_size Grid spacing
         * \note Calling forces a resize of the cell list on the next update
         */
        void setCellSize(Scalar cell_size)
            {
            m_cell_size = cell_size;
            m_max_grid_shift = 0.5 * m_cell_size;
            m_needs_compute_dim = true;
            }

        //! Get the MPCD cell size
        Scalar getCellSize() const
            {
            return m_cell_size;
            }

        #ifdef ENABLE_MPI
        //! Set the number of extra communication cells
        void setNExtraCells(unsigned int num_extra)
            {
            m_num_extra = num_extra;
            m_needs_compute_dim = true;
            }

        //! Get the number of extra communication cells
        unsigned int getNExtraCells() const
            {
            return m_num_extra;
            }

        //! Get the number of communication cells on each face of the box
        const std::array<unsigned int, 6>& getNComm() const
            {
            return m_num_comm;
            }

        //! Get the box that is covered by the cell list
        const BoxDim& getCoverageBox()
            {
            computeDimensions();
            return m_cover_box;
            }

        //! Check if communication is occurring along a direction
        bool isCommunicating(mpcd::detail::face dir);
        #endif // ENABLE_MPI

        //! Get the maximum permitted grid shift
        const Scalar getMaxGridShift() const
            {
            return m_max_grid_shift;
            }

        //! Set the grid shift vector
        void setGridShift(const Scalar3& shift)
            {
            if (std::fabs(shift.x) > m_max_grid_shift ||
                std::fabs(shift.y) > m_max_grid_shift ||
                std::fabs(shift.z) > m_max_grid_shift)
                {
                m_exec_conf->msg->error() << "mpcd: Specified cell list grid shift (" << shift.x
                                           << ", " << shift.y << ", " << shift.z << ")" << std::endl
                                           << "exceeds maximum component magnitude " << m_max_grid_shift << std::endl;
                throw std::runtime_error("Error setting MPCD grid shift");
                }

            m_grid_shift = shift;
            }

        // Get the grid shift vector
        const Scalar3& getGridShift() const
            {
            return m_grid_shift;
            }

        //! Calculate current cell occupancy statistics
        virtual void getCellStatistics() const;

        //! Gets the group of particles that is coupled to the MPCD solvent through the collision step
        std::shared_ptr<ParticleGroup> getEmbeddedGroup() const
            {
            return m_embed_group;
            }

        //! Sets a group of particles that is coupled to the MPCD solvent through the collision step
        void setEmbeddedGroup(std::shared_ptr<ParticleGroup> embed_group)
            {
            m_embed_group = embed_group;
            }

        //! Removes all embedded particles from collision coupling
        void removeEmbeddedGroup()
            {
            m_embed_group = std::shared_ptr<ParticleGroup>();
            }

        //! Gets the cell id array for the embedded particles
        const GPUArray<unsigned int>& getEmbeddedGroupCellIds() const
            {
            return m_embed_cell_ids;
            }

        #ifdef ENABLE_MPI
        //! Set the MPCD particle communicator
        virtual void setMPCDCommunicator(std::shared_ptr<mpcd::Communicator> comm)
            {
            m_mpcd_comm = comm;
            }
        #endif // ENABLE_MPI

    protected:
        std::shared_ptr<mpcd::ParticleData> m_mpcd_pdata;   //!< MPCD particle data
        std::shared_ptr<ParticleGroup> m_embed_group;     //!< Embedded particles

        Scalar3 m_grid_shift;   //!< Amount to shift particle positions when computing cell list
        Scalar m_max_grid_shift;    //!< Maximum amount grid can be shifted in any direction

        //! Allocates internal data arrays
        virtual void reallocate();

        Scalar m_cell_size;                         //!< MPCD cell width
        uint3 m_cell_dim;                           //!< Number of cells in each direction
        uint3 m_global_cell_dim;                    //!< Number of cells in each direction of global simulation box
        Index3D m_cell_indexer;                     //!< Indexer from 3D into cell list 1D
        Index2D m_cell_list_indexer;                //!< Indexer into cell list members
        unsigned int m_cell_np_max;                 //!< Maximum number of particles per cell
        GPUVector<unsigned int> m_cell_np;          //!< Number of particles per cell
        GPUVector<unsigned int> m_cell_list;        //!< Cell list of particles
        GPUVector<unsigned int> m_embed_cell_ids;   //!< Cell ids of the embedded particles
        GPUFlags<uint3> m_conditions;               //!< Detect conditions that might fail building cell list

        int3 m_origin_idx;                  //!< Origin as a global index

        #ifdef ENABLE_MPI
        unsigned int m_num_extra;               //!< Number of extra cells to communicate over
        std::array<unsigned int, 6> m_num_comm; //!< Number of cells to communicate on each face
        BoxDim m_cover_box;                     //!< Box covered by the cell list
        std::shared_ptr<mpcd::Communicator> m_mpcd_comm;    //!< MPCD particle communicator

        //! Determine if embedded particles require migration
        virtual bool needsEmbedMigrate(unsigned int timestep);
        #endif // ENABLE_MPI

        //! Check the condition flags
        bool checkConditions();

        //! Reset the conditions array
        void resetConditions();

        //! Builds the cell list and handles cell list memory
        void buildCellList();

    private:
        bool m_needs_compute_dim;   //!< True if the dimensions need to be (re-)computed
        //! Slot for box resizing
        void slotBoxChanged()
            {
            m_needs_compute_dim = true;
            }

        bool m_particles_sorted;    //!< True if any particles (MPCD or embedded) have been sorted
        //! Slot for particle sorting
        void slotSorted()
            {
            m_particles_sorted = true;
            }

        //! Update global simulation box and check that cell list is compatible with it
        void updateGlobalBox();

        #ifdef ENABLE_MPI
        std::shared_ptr<DomainDecomposition> m_decomposition;

        //! Checks neighboring domains to make sure they are properly overlapping
        void checkDomainBoundaries();
        #endif // ENABLE_MPI
    };

namespace detail
{
//! Export the CellList class to python
void export_CellList(pybind11::module& m);
} // end namespace detail

} // end namespace mpcd
#endif // MPCD_CELL_LIST_H_
