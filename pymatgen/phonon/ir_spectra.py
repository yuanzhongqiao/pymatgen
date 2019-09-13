# coding: utf-8
# Copyright (c) Pymatgen Development Team.
# Distributed under the terms of the MIT License.

from __future__ import unicode_literals

import numpy as np

from pymatgen.core.structure import Structure
from pymatgen.core.spectrum import Spectrum
from pymatgen.vis.plotters import SpectrumPlotter
from pymatgen.util.plotting import add_fig_kwargs, get_ax_fig_plt
from monty.json import MSONable

"""
This module provides classes to handle the calculation of the IR spectra
This implementation is adapted from Abipy
https://github.com/abinit/abipy
where it was originally done by Guido Petretto and Matteo Giantomassi
"""

__author__ = "Henrique Miranda, Guido Pettreto, Matteo Giantomassi"
__copyright__ = "Copyright 2018, The Materials Project"
__version__ = "0.1"
__maintainer__ = "Henrique Miranda"
__email__ = "miranda.henrique@gmail.com"
__date__ = "Oct 31, 2018"


class IRDielectricTensor(MSONable):
    """
    Class to handle the Ionic Dielectric Tensor
    The implementation is adapted from Abipy
    See the definitions Eq.(53-54) in :cite:`Gonze1997` PRB55, 10355 (1997).
    """
    def __init__(self, oscillator_strength, phfreqs_gamma, epsilon_infinity, structure):
        """
        Args:
            oscillatator_strength: IR oscillator strengths as defined
                                   in Eq. 54 in :cite:`Gonze1997` PRB55, 10355 (1997).
            phfreqs_gamma: Phonon frequencies at the Gamma point
            epsilon_infinity: electronic susceptibility as defined in Eq. 29.
            structure: A Structure object corresponding to the structure used for the calculation.
        """
        self.structure = structure
        self.oscillator_strength = np.array(oscillator_strength).real
        self.phfreqs_gamma = np.array(phfreqs_gamma)
        self.epsilon_infinity = np.array(epsilon_infinity)

    @classmethod
    def from_dict(cls, d):
        """
        Returns IRDielectricTensor from dict representation
        """
        structure = Structure.from_dict(d['structure'])
        oscillator_strength = d['oscillator_strength']
        phfreqs_gamma = d['phfreqs_gamma']
        epsilon_infinity = d['epsilon_infinity']
        return cls(oscillator_strength, phfreqs_gamma, epsilon_infinity, structure)

    @property
    def max_phfreq(self): return max(self.phfreqs_gamma)
    @property
    def nphfreqs(self): return len(self.phfreqs_gamma)

    def as_dict(self):
        """
        Json-serializable dict representation of IRDielectricTensor.
        """
        return {"@module": self.__class__.__module__,
                "@class": self.__class__.__name__,
                "oscillator_strength": self.oscillator_strength.tolist(),
                "phfreqs_gamma": self.phfreqs_gamma.tolist(),
                "structure": self.structure.as_dict(),
                "epsilon_infinity": self.epsilon_infinity.tolist()}

    def write_json(self, filename):
        """
        Save a json file with this data
        """
        import json
        with open(filename, 'w') as f:
            json.dump(self.as_dict(), f)

    def get_ir_spectra(self, broad=0.00005, emin=0, emax=None, divs=500):
        """
        The IR spectra is obtained for the different directions

        Args:
            broad: a list of broadenings or a single broadening for the phonon peaks
            emin, emax: minimum and maximum energy in which to obtain the spectra
            ndivs: number of frequency samples between emin and emax

        Returns:
            frequencies: ndivs array with the frequencies at which the
                         dielectric tensor is calculated
            dielectric_tensor: ndivsx3x3 numpy array with the dielectric tensor
                         for the range of frequencies
        """
        if isinstance(broad, float):
            broad = [broad]*self.nphfreqs
        if isinstance(broad, list) and len(broad) != self.nphfreqs:
            raise ValueError('The number of elements in the broad_list '
                             'is not the same as the number of frequencies')

        if emax is None:
            emax = self.max_phfreq + max(broad)*20
        frequencies = np.linspace(emin, emax, divs)

        na = np.newaxis
        dielectric_tensor = np.zeros((divs, 3, 3), dtype=complex)
        for i in range(3, len(self.phfreqs_gamma)):
            g = broad[i] * self.phfreqs_gamma[i]
            num = self.oscillator_strength[i, :, :]
            den = (self.phfreqs_gamma[i]**2 - frequencies[:, na, na]**2 - 1j*g)
            dielectric_tensor += num / den
        dielectric_tensor += self.epsilon_infinity[na, :, :]

        return frequencies, dielectric_tensor

    @add_fig_kwargs
    def plot(self, components=('xx',), reim="reim", show_phonon_frequencies=True, xlim=None, ylim=None, **kwargs):
        """
        Helper function to generate the Spectrum plotter and directly plot the results

        Arguments:
            components: A list with the components of the dielectric tensor to plot.
                        Can be either two indexes or a string like 'xx' to plot the (0,0) component
            reim: If 're' (im) is present in the string plots the real (imaginary) part of the dielectric tensor
            show_phonon_frequencies: plot a dot where the phonon frequencies are to help identify IR inactive modes
        """
        plotter = self.get_plotter(components=components, reim=reim, **kwargs)
        plt = plotter.get_plot(xlim=xlim, ylim=ylim)

        if show_phonon_frequencies:
            phfreqs_gamma = self.phfreqs_gamma[3:]
            plt.scatter(phfreqs_gamma*1000, np.zeros_like(phfreqs_gamma))
        plt.xlabel(r'$\epsilon(\omega)$')
        plt.xlabel(r'Frequency (meV)')
        return plt

    def get_plotter(self, components=('xx',), reim="reim", **kwargs):
        """
        Return an instance of the Spectrum plotter containing the different requested components

        Arguments:
            components: A list with the components of the dielectric tensor to plot.
                        Can be either two indexes or a string like 'xx' to plot the (0,0) component
            reim: If 're' (im) is present in the string plots the real (imaginary) part of the dielectric tensor
        """
        directions_map = {'x': 0, 'y': 1, 'z': 2, 0: 0, 1: 1, 2: 2}
        functions_map = {'re': lambda x: x.real, 'im': lambda x: x.imag}
        reim_label = {'re': 'Re', 'im': 'Im'}

        frequencies, dielectric_tensor = self.get_ir_spectra()

        plotter = SpectrumPlotter()
        for component in components:
            if not all([direction in directions_map.keys() for direction in component]) or len(component) != 2:
                raise ValueError('Invalid value found in components: {}'.format(component))
            i, j = [directions_map[direction] for direction in component]
            for fstr in functions_map:
                if fstr in reim:
                    f = functions_map[fstr]
                    label = r"%s{$\epsilon_{%s%s}$}" % (reim_label[fstr], 'xyz'[i], 'xyz'[j])
                    y = f(dielectric_tensor[:, i, j])
                    spectrum = Spectrum(frequencies*1000, y, label=label, **kwargs)
                    plotter.add_spectrum(label, spectrum)

        return plotter
