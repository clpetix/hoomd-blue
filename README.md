# HOOMD-blue

HOOMD-blue is a general purpose particle simulation toolkit. It performs molecular dynamics simulations of particles
with a variety of pair, bond, angle, and other potentials. HOOMD-blue runs fast on NVIDIA GPUs, and can scale across
many nodes. For more information, see the [HOOMD-blue website](https://codeblue.umich.edu/hoomd-blue).

# Installing HOOMD-blue

Official binaries of HOOMD-blue are available via [conda](http://conda.pydata.org/docs/) through
the [glotzer channel](https://anaconda.org/glotzer).
To install HOOMD-blue, first download and install
[miniconda](http://conda.pydata.org/miniconda.html) following [conda's instructions](http://conda.pydata.org/docs/install/quick.html).
Then add the `glotzer` channel and install HOOMD-blue:

```bash
$ conda config --add channels glotzer
$ conda install hoomd
```

# Compiling HOOMD-blue

Use cmake to configure an out of source build and make to build hoomd.

```bash
mkdir build
cd build
cmake ../
make -j20
```

For more detailed instructions, [see the documentationn](https://codeblue.umich.edu/hoomd-blue/doc/page_compile_guide.html).

## Prerequisites

 * Required:
     * Python >= 2.6
     * numpy >= 1.7
     * boost >= 1.39.0
     * CMake >= 2.6.2
     * C++ Compiler (tested with gcc, clang, intel)
 * Optional:
     * NVIDIA CUDA Toolkit >= 5.0
     * MPI (tested with OpenMPI, MVAPICH, impi)

# Job scripts

HOOMD-blue job scripts are python scripts. You can control system initialization, run protocol, analyze simulation data,
or develop complex workflows all with python code in your job.

Here is a simple example.

```python
from hoomd_script import *
context.initialize()

# create 100 random particles of name A
init.create_random(N=100, phi_p=0.01, name='A')
# specify Lennard-Jones interactions between particle pairs
lj = pair.lj(r_cut=3.0)
lj.pair_coeff.set('A', 'A', epsilon=1.0, sigma=1.0)
# integrate at constant temperature
all = group.all();
integrate.mode_standard(dt=0.005)
integrate.nvt(group=all, T=1.2, tau=0.5)
# run 10,000 time steps
run(10e3)
```

Save this as `lj.py` and run with `hoomd lj.py`.

# Documentation

Documentation for the current stable release is available online: [http://codeblue.umich.edu/hoomd-blue/doc/](http://codeblue.umich.edu/hoomd-blue/doc/)

# Change log

See [ChangeLog.md](ChangeLog.md).

# Contributing to HOOMD-blue.

See [CONTRIBUTING.md](CONTRIBUTING.md)
