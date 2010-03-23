/*
Highly Optimized Object-oriented Many-particle Dynamics -- Blue Edition
(HOOMD-blue) Open Source Software License Copyright 2008, 2009 Ames Laboratory
Iowa State University and The Regents of the University of Michigan All rights
reserved.

HOOMD-blue may contain modifications ("Contributions") provided, and to which
copyright is held, by various Contributors who have granted The Regents of the
University of Michigan the right to modify and/or distribute such Contributions.

Redistribution and use of HOOMD-blue, in source and binary forms, with or
without modification, are permitted, provided that the following conditions are
met:

* Redistributions of source code must retain the above copyright notice, this
list of conditions, and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice, this
list of conditions, and the following disclaimer in the documentation and/or
other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of HOOMD-blue's
contributors may be used to endorse or promote products derived from this
software without specific prior written permission.

Disclaimer

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDER AND CONTRIBUTORS ``AS IS''
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND/OR
ANY WARRANTIES THAT THIS SOFTWARE IS FREE OF INFRINGEMENT ARE DISCLAIMED.

IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/

// $Id$
// $URL$
// Maintainer: joaander

#include "TwoStepBDNVT.h"

#ifndef __TWO_STEP_BDNVT_GPU_H__
#define __TWO_STEP_BDNVT_GPU_H__

/*! \file TwoStepBDNVTGPU.h
    \brief Declares the TwoStepBDNVTGPU class
*/

//! Integrates part of the system forward in two steps in the NVT ensemble (via brownian dynamics)
/*! Implements velocity-verlet NVE integration with additional brownian dynamics forces through the
    IntegrationMethodTwoStep interface, runs on the GPU.
    
    This class must inherit from TwoStepBDNVT so that it has that interface. However, is based off of the NVE
    integration base routines. Rather than doing some evil multiple inheritance here, the integrateStepOne() from
    TwoStepNVEGPU will simply be duplicated here.
    
    In order to implement integrateStepTwo with the added BD forces, integrateStepTwo needs is reimplemened for
    BDNVT.
    
    \ingroup updaters
*/
class TwoStepBDNVTGPU : public TwoStepBDNVT
    {
    public:
        //! Constructs the integration method and associates it with the system
        TwoStepBDNVTGPU(boost::shared_ptr<SystemDefinition> sysdef,
                        boost::shared_ptr<ParticleGroup> group,
                        boost::shared_ptr<Variant> T,
                        unsigned int seed,
                        bool gamma_diam);
        virtual ~TwoStepBDNVTGPU() {};
        
        //! Performs the first step of the integration
        virtual void integrateStepOne(unsigned int timestep);
        
        //! Performs the second step of the integration
        virtual void integrateStepTwo(unsigned int timestep);
      
    protected:
        unsigned int m_block_size;              //!< block size for partial sum memory
        unsigned int m_num_blocks;              //!< number of memory blocks reserved for partial sum memory
        GPUArray<float> m_partial_sum1;         //!< memory space for partial sum over bd energy transfers
        GPUArray<float> m_sum;                  //!< memory space for sum over bd energy transfers          
    };

//! Exports the TwoStepBDNVTGPU class to python
void export_TwoStepBDNVTGPU();

#endif // #ifndef __TWO_STEP_BDNVT_GPU_H__

