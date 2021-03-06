# coding: utf-8
"""This module ..."""
from __future__ import print_function, division, unicode_literals, absolute_import

import abc
import os
import six
import collections
import tempfile
import pickle

from time import ctime
from monty.os.path import which
from monty.termcolor import cprint
from monty.string import is_string
from monty.functools import lazy_property

from abipy.iotools.cube import cube_read_structure_mesh_data
from abipy.flowtk.netcdf import NetcdfReader, NO_DEFAULT


__all__ = [
    "AbinitNcFile",
    "Has_Structure",
    "Has_ElectronBands",
    "Has_PhononBands",
    "NotebookWriter",
    #"Has_Header",
    #"AbinitHeader",
]

@six.add_metaclass(abc.ABCMeta)
class _File(object):
    """
    Abstract base class defining the methods that must be implemented
    by the concrete classes representing the different files produced by ABINIT.
    """
    def __init__(self, filepath):
        self._filepath = os.path.abspath(filepath)

        # Save stat values
        stat = os.stat(filepath)
        self._last_atime = stat.st_atime
        self._last_mtime = stat.st_mtime
        self._last_ctime = stat.st_ctime

    def __repr__(self):
        return "<%s, %s>" % (self.__class__.__name__, self.relpath)

    @classmethod
    def from_file(cls, filepath):
        """Initialize the object from a string."""
        if isinstance(filepath, cls):
            return filepath

        #print("Perhaps the subclass", cls, "must redefine the classmethod from_file.")
        return cls(filepath)

    @property
    def filepath(self):
        """Absolute path of the file."""
        return self._filepath

    @property
    def relpath(self):
        """Relative path."""
        try:
            return os.path.relpath(self.filepath)
        except OSError:
            # current working directory may not be defined!
            return self.filepath

    @property
    def basename(self):
        """Basename of the file."""
        return os.path.basename(self.filepath)

    @property
    def filetype(self):
        """String defining the filetype."""
        return self.__class__.__name__

    def filestat(self, as_string=False):
        """
        Dictionary with file metadata
        if `as_string` is True, a string is returned.
        """
        d = get_filestat(self.filepath)
        if not as_string: return d
        return "\n".join("%s: %s" % (k, v) for k, v in d.items())

    @abc.abstractmethod
    def close(self):
        """Close file."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Activated at the end of the with statement. It automatically closes the file."""
        self.close()

    #def __del__(self):
    #    """
    #    Called when the instance is about to be destroyed.
    #    """
    #    try:
    #        self.close()
    #    finally:
    #        super(_File, self).__close__(self)


class TextFile(_File):

    def __enter__(self):
        # Open the file
        self._file
        return self

    def __iter__(self):
        return iter(self._file)

    @lazy_property
    def _file(self):
        """File object open in read-only mode."""
        return open(self.filepath, mode="rt")

    def close(self):
        """Close the file."""
        try:
            self._file.close()
        except:
            pass

    def seek(self, offset, whence=0):
        """Set the file's current position, like stdio's fseek()."""
        self._file.seek(offset, whence)


class AbinitOutNcFile(NetcdfReader):
    """
    Class representing the _OUT.nc file.
    """

    def get_vars(self, vars, strict=False):
        # TODO: add a check on the variable names ?
        default = NO_DEFAULT if strict else None
        var_values = {}
        for var in vars:
            var_values[var] = self.read_value(varname=var, default=default)
        return var_values


@six.add_metaclass(abc.ABCMeta)
class AbinitNcFile(_File):
    """
    Abstract class representing a Netcdf file with data saved
    according to the ETSF-IO specifications (when available).
    """
    def ncdump(self, *nc_args, **nc_kwargs):
        """Returns a string with the output of ncdump."""
        return NcDumper(*nc_args, **nc_kwargs).dump(self.filepath)


@six.add_metaclass(abc.ABCMeta)
class AbinitFortranFile(_File):
    """
    Abstract class representing a fortran file containing
    output data from abinit.
    """
    def close(self):
        pass


class CubeFile(_File):
    """

    .. attribute:: structure

        :class:`Structure` object

    .. attribute:: mesh

        :class:`Mesh3d` object with information on the uniform 3d mesh.

    .. attribute:: data

        numpy array of shape [nx, ny, nz] with numerical values on the real-space mesh.
    """
    def __init__(self, filepath):
        from abipy.iotools.cube import cube_read_structure_mesh_data
        super(CubeFile, self).__init__(filepath)
        self.structure, self.mesh, self.data = cube_read_structure_mesh_data(self.filepath)

    def close(self):
        """nop, just to fulfill the abstract interface."""

    #@classmethod
    #def write_structure_mesh_data(cls, path, structure, mesh, data):
    #    with open(path, "wt") as fh:
    #        cube_write_structure_mesh(fh, structure, mesh)
    #        cube_write_data(fh, data, mesh):


@six.add_metaclass(abc.ABCMeta)
class Has_Structure(object):
    """Mixin class for :class:`AbinitNcFile` containing crystallographic data."""

    @abc.abstractproperty
    def structure(self):
        """Returns the :class:`Structure` object."""

    def plot_bz(self, **kwargs):
        """
        Gives the plot (as a matplotlib object) of the symmetry line path in the Brillouin Zone.
        """
        return self.structure.plot_bz(**kwargs)

    # To maintain backward compatbility
    show_bz = plot_bz

    def export_structure(self, filepath):
        """
        Export the structure on file.

        returns:
            Instance of :class:`Visualizer`
        """
        return self.structure.export(filepath)

    def visualize_structure_with(self, visu_name):
        """
        Visualize the crystalline structure with the specified visualizer.

        See :class:`Visualizer` for the list of applications and formats supported.
        """
        from abipy.iotools.visualizer import Visualizer
        visu = Visualizer.from_name(visu_name)

        for ext in visu.supported_extensions():
            ext = "." + ext
            try:
                return self.export_structure(ext)
            except visu.Error:
                pass
        else:
            raise visu.Error("Don't know how to export data for visu_name %s" % visu_name)


@six.add_metaclass(abc.ABCMeta)
class Has_ElectronBands(object):
    """Mixin class for :class:`AbinitNcFile` containing electron data."""

    @abc.abstractproperty
    def ebands(self):
        """Returns the :class:`ElectronBands` object."""

    @property
    def nsppol(self):
        """Number of spin polarizations"""
        return self.ebands.nsppol

    @property
    def nspinor(self):
        """Number of spinors"""
        return self.ebands.nspinor

    @property
    def nspden(self):
        """Number of indepedendent spin-density components."""
        return self.ebands.nspden

    @property
    def mband(self):
        """Maximum number of bands."""
        return self.ebands.mband

    @property
    def nband(self):
        """Maximum number of bands."""
        return self.ebands.nband

    @property
    def nelect(self):
        """Number of elecrons per unit cell"""
        return self.ebands.nelect

    @property
    def nkpt(self):
        """Number of k-points."""
        return self.ebands.nkpt

    @property
    def kpoints(self):
        """Iterable with the Kpoints."""
        return self.ebands.kpoints

    def plot_ebands(self, **kwargs):
        """Plot the electron energy bands. See the :func:`ElectronBands.plot` for the signature."""
        return self.ebands.plot(**kwargs)

    def plot_ebands_with_edos(self, dos, **kwargs):
        return self.ebands.plot_with_edos(dos, **kwargs)


@six.add_metaclass(abc.ABCMeta)
class Has_PhononBands(object):
    """Mixin class for :class:`AbinitNcFile` containing phonon data."""

    @abc.abstractproperty
    def phbands(self):
        """Returns the :class:`PhononBands` object."""

    def plot_phbands(self, **kwargs):
        """
        Plot the electron energy bands. See the :func:`PhononBands.plot` for the signature.""
        """
        return self.phbands.plot(**kwargs)

    #def plot_phbands_with_phdos(self, phdos, **kwargs):
    #    return self.phbands.plot_with_phdos(phdos, **kwargs)


class NcDumper(object):
    """Wrapper object for the ncdump tool."""

    def __init__(self, *nc_args, **nc_kwargs):
        """
        Args:
            nc_args: Arguments passed to ncdump.
            nc_kwargs: Keyword arguments passed to ncdump
        """
        self.nc_args = nc_args
        self.nc_kwargs = nc_kwargs
        self.ncdump = which("ncdump")

    def dump(self, filepath):
        """Returns a string with the output of ncdump."""
        if self.ncdump is None:
            return "Cannot find ncdump tool in PATH"
        else:
            from subprocess import check_output
            return check_output(["ncdump", filepath])


_ABBREVS = [
    (1 << 50, 'Pb'),
    (1 << 40, 'Tb'),
    (1 << 30, 'Gb'),
    (1 << 20, 'Mb'),
    (1 << 10, 'kb'),
    (1, 'b'),
]


def size2str(size):
    """Convert size to string with units."""
    for factor, suffix in _ABBREVS:
        if size > factor:
            break
    return "%.2f " % (size / factor) + suffix


def get_filestat(filepath):
    stat = os.stat(filepath)
    return collections.OrderedDict([
        ("Name", os.path.basename(filepath)),
        ("Directory", os.path.dirname(filepath)),
        ("Size", size2str(stat.st_size)),
        ("Access Time", ctime(stat.st_atime)),
        ("Modification Time", ctime(stat.st_mtime)),
        ("Change Time", ctime(stat.st_ctime)),
    ])


@six.add_metaclass(abc.ABCMeta)
class NotebookWriter(object):
    """
    Mixin class for objects that are able to generate jupyter notebooks.
    Subclasses must provide a concrete implementation of `write_notebook`.
    """
    def make_and_open_notebook(self, nbpath=None, foreground=False):
        """
        Generate an ipython notebook and open it in the browser.

        Args:
            nbpath: If nbpath is None, a temporay file is created.
            foreground: By default, jupyter is executed in background and stdout, stderr are redirected
            to devnull. Use foreground to run the process in foreground

        Return:
            system exit code.

        Raise:
            RuntimeError if jupyter is not in $PATH
        """
        nbpath = self.write_notebook(nbpath=nbpath)

        if which("jupyter") is None:
            raise RuntimeError("Cannot find jupyter in PATH. Install it with `conda install jupyter or `pip install jupyter`")

        if foreground:
            return os.system("jupyter notebook %s" % nbpath)
        else:
            fd, tmpname = tempfile.mkstemp(text=True)
            print(tmpname)
            cmd = "jupyter notebook %s" % nbpath
            print("Executing:", cmd)
            print("stdout and stderr redirected to %s" % tmpname)
            import subprocess
            process = subprocess.Popen(cmd.split(), shell=False, stdout=fd, stderr=fd)
            cprint("pid: %s" % str(process.pid), "yellow")

    def get_nbformat_nbv_nb(self, title=None):
        """
        """
        import nbformat
        nbv = nbformat.v4
        nb = nbv.new_notebook()

        if title is not None:
            nb.cells.append(nbv.new_markdown_cell("## %s" % title))

        nb.cells.extend([
            nbv.new_code_cell("""\
from __future__ import print_function, division, unicode_literals, absolute_import

import sys, os
import numpy as np

%matplotlib notebook
from IPython.display import display

# Uncomment this line to activate seaborn settings.
#import seaborn as sns

# This to render pandas DataFrames with https://github.com/quantopian/qgrid
#import qgrid
#qgrid.nbinstall(overwrite=True)  # copies javascript dependencies to your /nbextensions folder

# This to view Mayavi visualizations. See http://docs.enthought.com/mayavi/mayavi/tips.html
#from mayavi import mlab; mlab.init_notebook(backend='x3d', width=None, height=None, local=True)

from abipy import abilab""")
        ])

        return nbformat, nbv, nb

    @abc.abstractmethod
    def write_notebook(self, nbpath=None):
        """
        Write an ipython notebook to nbpath. If nbpath is None, a temporay file is created.
        Return path to the notebook. A typical template is given below.
        """
        # Preable.
        nbformat, nbv, nb = self.get_nbformat_nbv_nb(title=None)

        #####################
        # Put your code here
        nb.cells.extend([
            nbv.new_markdown_cell("# This is a markdown cell"),
            nbv.new_code_cell("a = 1"),
        ])
        #####################

        # Call _write_nb_nbpath
        return self._write_nb_nbpath(nb, nbpath)

    @staticmethod
    def _write_nb_nbpath(nb, nbpath):
        """
        This method must be called at the end of `write_notebook`.
        nb is the ipython notebook and nbpath the argument passed to `write_notebook`.
        """
        import io, os, tempfile
        if nbpath is None:
            _, nbpath = tempfile.mkstemp(prefix="abinb_", suffix='.ipynb', dir=os.getcwd(), text=True)

        # Write notebook
        import nbformat
        with io.open(nbpath, 'wt', encoding="utf8") as fh:
            nbformat.write(nb, fh)
            return nbpath

    @classmethod
    def pickle_load(cls, filepath):
        """
        Loads the object from a pickle file
        """
        with open(filepath, "rb") as fh:
            new = pickle.load(fh)
            #assert cls is new.__class__
            return new

    def pickle_dump(self, filepath=None):
        """
        Save the status of the object in pickle format.
        If filepath is None, a temporary file is created.

        Return:
            name of the pickle file.
        """
        if filepath is None:
            _, filepath = tempfile.mkstemp(suffix='.pickle')

        with open(filepath, "wb") as fh:
            pickle.dump(self, fh)
            return filepath

#class Has_AbinitHeader(object)
#    @lazy_property
#    def hdr(self)
#        return self.reader.read_hdr()
