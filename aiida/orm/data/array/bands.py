# -*- coding: utf-8 -*-
"""
This module defines the classes related to band structures or dispersions
in a Brillouin zone, and how to operate on them.
"""

from aiida.orm.data.array.kpoints import KpointsData
import numpy
from string import Template
from aiida.common.exceptions import ValidationError

__copyright__ = u"Copyright (c), 2014-2015, École Polytechnique Fédérale de Lausanne (EPFL), Switzerland, Laboratory of Theory and Simulation of Materials (THEOS). All rights reserved."
__license__ = "Non-Commercial, End-User Software License Agreement, see LICENSE.txt file"
__version__ = "0.4.1"

#TODO: set and get bands could have more functionalities: how do I know the number of bands for example?

def find_bandgap(bandsdata, number_electrons=None, fermi_energy=None):
    """
    Tries to guess whether the bandsdata represent an insulator.
    This method is meant to be used only for electronic bands (not phonons)
    By default, it will try to use the occupations to guess the number of 
    electrons and find the Fermi Energy, otherwise, it can be provided 
    explicitely.
    Also, there is an implicit assumption that the kpoints grid is 
    "sufficiently" dense, so that the bandsdata are not missing the 
    intersection between valence and conduction band if present. 
    Use this function with care!
    
    :param (float) number_electrons: (optional) number of electrons in the unit cell
    :param (float) fermi_energy: (optional) value of the fermi energy. 
    
    :note: By default, the algorithm uses the occupations array
      to guess the number of electrons and the occupied bands. This is to be 
      used with care, because the occupations could be smeared so at a 
      non-zero temperature, with the unwanted effect that the conduction bands
      might be occupied in an insulator.
      Prefer to pass the number_of_electrons explicitly
      
    :note: Only one between number_electrons and fermi_energy can be specified at the 
      same time.
    
    :return: (is_insulator, gap), where is_insulator is a boolean, and gap a 
             float. The gap is None in case of a metal, zero when the homo is 
             equal to the lumo (e.g. in semi-metals).
    """
    def nint(num):
        """
        Stable rounding function
        """
        if (num > 0):
            return int(num+.5)
        else:
            return int(num-.5)
    
    if fermi_energy and number_electrons:
        raise ValueError("Specify either the number of electrons or the "
                         "Fermi energy, but not both")
            
    try:
        stored_bands = bandsdata.get_bands()
    except KeyError:
        raise KeyError("Cannot do much of a band analysis without bands")
    
    if len(stored_bands.shape)==3:
        # I write the algorithm for the generic case of having both the 
        # spin up and spin down array
        
        # put all spins on one band per kpoint
        bands = numpy.concatenate( [_ for _ in stored_bands],axis=1 )
    else:
        bands = stored_bands
        
    # analysis on occupations:
    if fermi_energy is None:
        
        num_kpoints = len(bands)
        
        if number_electrons is None:
            try:
                _,stored_occupations = bandsdata.get_bands(also_occupations=True)
            except KeyError:
                    raise KeyError("Cannot determine metallicity if I don't have "
                                   "either fermi energy, or occupations")
            
            # put the occupations in the same order of bands, also in case of multiple bands
            if len(stored_occupations.shape)==3:
                # I write the algorithm for the generic case of having both the 
                # spin up and spin down array
                
                # put all spins on one band per kpoint
                occupations = numpy.concatenate( [_ for _ in stored_occupations],axis=1 )
            else:
                occupations = stored_occupations
        
            # now sort the bands by energy
            # Note: I am sort of assuming that I have an electronic ground state
            
            # sort the bands by energy, and reorder the occupations accordingly 
            # since after joining the two spins, I might have unsorted stuff
            bands, occupations = [ numpy.array(y) for y in zip(*[zip(*j) for j in 
                                                [sorted(zip(i[0].tolist(),i[1].tolist()),
                                                        key=lambda x: x[0])
                                                 for i in zip(bands,occupations)]])]
            number_electrons = int(round( sum( [sum(i) for i in occupations] )/num_kpoints ))
        
            homo_indexes = [ numpy.where( numpy.array([ nint(_) for _ in x]) >0 )[0][-1] for x in occupations ]
            if len(set(homo_indexes))>1: # there must be intersections of valence and conduction bands
                return False, None
            else:
                homo = [ _[0][_[1]] for _ in zip(bands,homo_indexes) ]
                try:
                    lumo = [ _[0][_[1]+1] for _ in zip(bands,homo_indexes) ]
                except IndexError:
                    raise ValueError("To understand if it is a metal or insulator, "
                                         "need more bands than n_band=number_electrons")
        
        else:
            bands = numpy.sort(bands)
            number_electrons = int(number_electrons)
            
            # find the zero-temperature occupation per band (1 for spin-polarized
            # calculation, 2 otherwise)
            number_electrons_per_band = 4-len(stored_bands.shape) # 1 or 2
            # gather the energies of the homo band, for every kpoint
            homo = [ i[number_electrons/number_electrons_per_band-1] for i in bands ] # take the nth level
            try:
                # gather the energies of the lumo band, for every kpoint
                lumo = [ i[number_electrons/number_electrons_per_band] for i in bands ] # take the n+1th level
            except IndexError:
                raise ValueError("To understand if it is a metal or insulator, "
                                     "need more bands than n_band=number_electrons")
        
        if number_electrons%2==1 and len(stored_bands.shape)==2:
            # if #electrons is odd and we have a non spin polarized calculation
            # it must be a metal and I don't need further checks
            return False, None

        # if the nth band crosses the (n+1)th, it is an insulator
        gap = min(lumo) - max(homo)
        if gap == 0.:
            return False, 0.
        elif gap < 0.:
            return False, None
        else:
            return True, gap
    
    # analysis on the fermi energy
    else:
        # reorganize the bands, rather than per kpoint, per energy level
        
        # I need the bands sorted by energy
        bands.sort()
        
        levels = bands.transpose()
        max_mins = [ (max(i),min(i)) for i in levels]
        
        if fermi_energy > bands.max():
            raise ValueError("The Fermi energy is above all band energies, "
                             "don't know what to do")
        if fermi_energy < bands.min():
            raise ValueError("The Fermi energy is below all band energies, "
                             "don't know what to do.")
        
        # one band is crossed by the fermi energy
        if any( i[1]<fermi_energy and fermi_energy<i[0] for i in max_mins ):
            return False, None
        
        # case of semimetals, fermi energy at the crossing of two bands
        # this will only work if the dirac point is computed!
        elif ( any( i[0]==fermi_energy for i in max_mins ) and
                 any( i[1]==fermi_energy for i in max_mins ) ):
                return False, 0.
        # insulating case
        else:
            # take the max of the band maxima below the fermi energy
            homo = max( [ i[0] for i in max_mins if i[0]<fermi_energy ] )
            # take the min of the band minima above the fermi energy
            lumo = min( [ i[1] for i in max_mins if i[1]>fermi_energy ] )
            gap = lumo - homo
            if gap <= 0.:
                raise Exception("Something wrong has been implemented. "
                                "Revise the code!")
            return True, gap
    

class BandsData(KpointsData):
    """
    Class to handle bands data  
    """

    def set_kpointsdata(self,kpointsdata):
        """
        Load the kpoints from a kpoint object.
        :param kpointsdata: an instance of KpointsData class
        """
        if not isinstance(kpointsdata,KpointsData):
            raise ValueError("kpointsdata must be of the KpointsData class")
        try:
            self.cell = kpointsdata.cell
        except AttributeError:
            pass
        try:
            self.pbc=kpointsdata.pbc
        except AttributeError:
            pass
        try:
            self.bravais_lattice = kpointsdata.bravais_lattice
        except AttributeError:
            pass
        try:
            the_kpoints =  kpointsdata.get_kpoints()
        except AttributeError:
            the_kpoints = None
        try:
            the_weights=kpointsdata.get_kpoints(also_weights=True)[1]
        except AttributeError:
            the_weights = None
        self.set_kpoints(the_kpoints, weights=the_weights)
        try:
            self.labels = kpointsdata.labels
        except (AttributeError,TypeError):
            self.labels = []
        
    def _validate_bands_occupations(self, bands, occupations=None, labels=None):
        """
        Validate the list of bands and of occupations before storage.
        Kpoints must be set in advance.
        Bands and occupations must be convertible into arrays of 
        Nkpoints x Nbands floats or Nspins x Nkpoints x Nbands; Nkpoints must 
        correspond to the number of kpoints.
        """
        try:
            kpoints = self.get_kpoints()
        except AttributeError:
            raise AttributeError("Must first set the kpoints, then the bands")

        the_bands = numpy.array(bands)
        
        if len(the_bands.shape) not in [2,3]:
            raise ValueError("Bands must be an array of dimension 2"
                             "([N_kpoints, N_bands]) or of dimension 3 "
                             " ([N_arrays, N_kpoints, N_bands]), found instead {}"
                             .format(len(the_bands.shape)))
        
        list_of_arrays_to_be_checked = []
        
        # check that the shape of everything is consistent with the kpoints
        num_kpoints_from_bands = the_bands.shape[0] if len(the_bands.shape)==2 else the_bands.shape[1]
        if num_kpoints_from_bands != len(kpoints):
            raise ValueError("There must be energy values for every kpoint") 
        
        if occupations is not None:
            the_occupations = numpy.array(occupations)
            if the_occupations.shape != the_bands.shape:
                raise ValueError("Shape of occupations {} different from shape"
                                 "shape of bands {}".format(the_occupations.shape,
                                 the_bands.shape))
            
            if not the_bands.dtype.type == numpy.float64:
                list_of_arrays_to_be_checked.append([the_occupations,'occupations'])
        else:
            the_occupations = None
            #list_of_arrays_to_be_checked = [ [the_bands,'bands'] ]
        
        # check that there every element is a float
        if not the_bands.dtype.type == numpy.float64:
            list_of_arrays_to_be_checked.append( [the_bands,'bands'] )
            
        for x,msg in list_of_arrays_to_be_checked:
            try:
                [ float(_) for _ in x.flatten() if _ is not None ]
            except (TypeError,ValueError):
                raise ValueError("The {} array can only contain "
                                 "float or None values".format(msg))
        
        # check the labels
        if labels is not None:
            if isinstance(labels,basestring):
                the_labels = [str(labels)]
            elif isinstance(labels,(tuple,list)) and all( [isinstance(_,basestring) for _ in labels] ):
                the_labels = [str(_) for _ in labels]
            else:
                raise ValidationError("Band labels have an unrecognized type ({})"
                                      "but should be a string or a list of strings".format(labels.__class__))
                
            if len(the_bands.shape)==2 and len(the_labels) != 1:
                raise ValidationError("More array labels than the number of arrays")
            elif len(the_bands.shape)==3 and len(the_labels) != the_bands.shape[0]:
                raise ValidationError("More array labels than the number of arrays")
        else:
            the_labels = None
            
        return the_bands,the_occupations, the_labels



    def set_bands(self,bands,units=None,occupations=None, labels=None):
        """
        Set an array of band energies of dimension (nkpoints x nbands).
        Kpoints must be set in advance. Can contain floats or None.
        :param bands: a list of nkpoints lists of nbands bands, or a 2D array 
                of shape (nkpoints x nbands), with band energies for each kpoint
        :param units: optional, energy units
        :param occupations: optional, a 2D list or array of floats of same shape 
                as bands, with the occupation associated to each band 
        """
        # checks bands and occupations 
        the_bands, the_occupations, the_labels = self._validate_bands_occupations(bands,
                                                                                  occupations,
                                                                                  labels)
        # set bands and their units
        self.set_array('bands',the_bands)
        self.units = units
        
        if the_labels is not None:
            self._set_attr('array_labels',the_labels)
        
        if the_occupations is not None:
            # set occupations
            self.set_array('occupations',the_occupations)

    @property
    def array_labels(self):
        """
        Get the labels associated with the band arrays
        """
        return self.get_attr('array_labels',None)
    
    @property
    def units(self):
        """
        Units in which the data in bands were stored. A string
        """
        #return copy.deepcopy(self._pbc)
        return self.get_attr('units')

    @units.setter
    def units(self,value):
        """
        Set the value of pbc, i.e. a tuple of three booleans, indicating if the
        cell is periodic in the 1,2,3 crystal direction
        """
        the_str = str(value)
        self._set_attr('units',the_str)

    def _set_pbc(self, value):
        """
        validate the pbc, then store them
        """
        from aiida.common.exceptions import ModificationNotAllowed
        from aiida.orm.data.structure import get_valid_pbc

        if not self._to_be_stored:
            raise ModificationNotAllowed(
                            "The KpointsData object cannot be modified, "
                            "it has already been stored")
        the_pbc = get_valid_pbc(value)
        self._set_attr('pbc1',the_pbc[0])
        self._set_attr('pbc2',the_pbc[1])
        self._set_attr('pbc3',the_pbc[2])


    def get_bands(self, also_occupations=False, also_labels=False):
        """
        Returns an array (nkpoints x num_bands or nspins x nkpoints x num_bands)
        of energies.
        :param also_occupations: if True, returns also the occupations array. 
            Default = False
        """
        try:
            bands=numpy.array(self.get_array('bands'))
        except KeyError:
            raise AttributeError("No stored bands has been found")
        
        to_return = [bands]
        
        if also_occupations:
            try:
                occupations = numpy.array(self.get_array('occupations'))
            except KeyError:
                raise AttributeError('No occupations were set')
            to_return.append(occupations)

        if also_labels:
            to_return.append(self.array_labels)
        
        if len(to_return)==1:
            return bands
        else:
            return to_return
        
    def _exportstring(self, fileformat,path=None,comments=True,cartesian=True,
                        **kwargs):
        """
        Export the bands to a string.
        :param fileformat: format of the file created (e.g. 'agr').
        :param path: absolute path of the file to be created (used for 
                additional files, and put in plot_info['filename'])
        :param comments: if True, append some extra informations at the 
                beginning of the file.
        :param cartesian: if True, distances (for the x-axis) are computed in
                cartesian coordinates, otherwise they are computed in reciprocal
                coordinates. cartesian=True will fail if no cell has been set.
        :param **kwargs: additional parameters to be passed to the 
                _prepare_[fileformat] method
                
        :note: this function will NOT produce nice plots if:
              - there is no path of kpoints, but a set of isolated points
              - the path is not continuous AND no labels are set  
        """
        #TODO: check for None in bands
        import os
        from aiida import get_file_header
        
        preparer_name = "_prepare_" + fileformat
        
        # load the x and y's of the graph
        stored_bands = self.get_bands()
        if len(stored_bands.shape)==2:
            bands = stored_bands
        elif len(stored_bands.shape)==3:
            bands = numpy.concatenate( [_ for _ in stored_bands],axis=1 )
        else:
            raise ValueError("Unexpected shape of bands")
        
        # here I build the x distances on the graph (in cartesian coordinates 
        # if cartesian==True AND if the cell was set, otherwise in reciprocal
        # coordinates)
        try:
            kpoints = self.get_kpoints(cartesian=cartesian)
        except AttributeError:
            # this error is happening if cartesian==True and if no cell has been
            # set -> we switch to reciprocal coordinates to compute distances
            kpoints = self.get_kpoints()
        # I take advantage of the path to recognize discontinuities
        try:
            labels = self.labels
            labels_indices = [i[0] for i in labels]
        except (AttributeError,TypeError):
            labels = []
            labels_indices = []
            
        # since I can have discontinuous paths, I set on those points the distance to zero
        # as a result, where there are discontinuities in the path, 
        # I have two consecutive points with the same x coordinate
        distances = [ numpy.linalg.norm( kpoints[i]-kpoints[i-1] ) if not  
                      (i in labels_indices and i-1 in labels_indices) else 0. 
                      for i in range(1,len(kpoints)) ]
        x = [ float(sum(distances[:i])) for i in range(len(distances)+1) ]

        # transform the index of the labels in the coordinates of x
        the_labels = [ (x[i[0]],i[1]) for i in labels ]
        
        if the_labels:
            new_labels = [list(the_labels[0])]
            # modify labels when in overlapping position
            j=0
            for i in range(1,len(the_labels)):
                if new_labels[j][1] == 'G' and 'agr' in fileformat:
                    new_labels[j][1] = r"\xG"
                if the_labels[i][0]==the_labels[i-1][0]:
                    new_labels[j][1] += "|" + the_labels[i][1]
                else:
                    new_labels.append(list(the_labels[i]))
                    j+=1
            if new_labels[j][1] == 'G' and 'agr' in fileformat:
                new_labels[j][1] = r"\xG"
            
        else:
            new_labels = []
        
        plot_info = {}
        plot_info['x'] = x
        plot_info['y'] = bands
        plot_info['labels'] = new_labels
        if path:
            plot_info['filename'] = path
            if fileformat == 'agr':
                plot_info['filename'] = os.path.splitext(path)[0] + '.dat'
        
        # generic info
        if comments:
            filetext = []
            #filetext.append("{}".format(get_file_header()))
            filetext.append( "# Dumped from BandsData UUID={}"
                             .format(self.uuid) )
            filetext.append("#\tpoints\tbands")
            filetext.append("#\t{}\t{}".format(*bands.shape))
            filetext.append("# \tlabel\tpoint")
            for l in new_labels:
                filetext.append( "#\t{}\t{:.8f}".format(l[1],l[0]) )
            filetext = get_file_header() + "#\n" + "\n".join(filetext) + "\n\n"
        else:
            filetext=""
            
        try:
            newfiletext,extra_files = getattr(self,preparer_name)(plot_info, **kwargs)
            filetext += newfiletext
        except AttributeError:
            raise
#            raise ValueError("Format {} is not valid".format(fileformat))
        
        if extra_files is not None:
            return filetext,extra_files
        else:
            return filetext
        
    def export(self,path,fileformat=None,overwrite=False,comments=True,
               cartesian=True,**kwargs):
        """
        Export the bands to a file.
        :param path: absolute path of the file to be created
        :param fileformat: format of the file created. If None, tries to use the 
                     extension of path to understand the correct one.
        :param overwrite: if set to True, overwrites file found at path. Default=False
        :param comments: if True, append some extra informations at the 
                beginning of the file.
        :param cartesian: if True, distances (for the x-axis) are computed in
                cartesian coordinates, otherwise they are computed in reciprocal
                coordinates. cartesian=True will fail if no cell has been set.
        :param **kwargs: additional parameters to be passed to the 
                _prepare_[fileformat] method
                
        :note: this function will NOT produce nice plots if:
              - there is no path of kpoints, but a set of isolated points
              - the path is not continuous AND no labels are set  
        """
        import os
        
        if not path:
            raise ValueError("Path not recognized")
        
        if os.path.exists(path) and not overwrite:
            raise OSError("A file was already found at {}".format(path))
        
        if fileformat is None:
            extension = os.path.splitext(path)[1].split('.')[1]
            if not extension:
                raise ValueError("Cannot recognized the fileformat from the "
                                 "extension")
            fileformat = extension
            if extension == 'dat':
                fileformat = 'dat_1'
        
        try:
            filetext,extra_files = self._exportstring(fileformat,path=path,
                                        comments=comments,cartesian=cartesian,
                                        **kwargs)
        except ValueError:
            extra_files = None
            filetext = self._exportstring(fileformat,path=path,
                                      comments=comments,cartesian=cartesian,
                                      **kwargs)

        if extra_files is not None:
            # write extra files
            for k,v in extra_files.iteritems():
                if os.path.exists(k) and not overwrite:
                    raise OSError("A file was already found: {}".format(k) )
                else:
                    with open( k,"w" ) as f:
                        f.write(v)
        
        with open(path,'w') as f:
            f.write(filetext)
        
    def get_export_formats(self):
        names = dir(self)
        return [ i.split('_prepare_')[1] for i in names if i.startswith('_prepare_') ]
        
    def _prepare_agr_batch(self,plot_info,**kwargs):
        """
        Prepare two files, data and batch, to be plot with xmgrace as:
        xmgrace -batch file.dat
        """
        if kwargs:
            raise TypeError("_prepare_agr_batch takes no keyword arguments")
        
        bands = plot_info['y']
        x = plot_info['x']
        labels = plot_info['labels']
        
        num_labels = len(labels)
        num_bands = bands.shape[1]

        # axis limits
        y_max_lim = bands.max()
        y_min_lim = bands.min()
        x_min_lim = min(x) # this isn't a numpy array, but a list
        x_max_lim = max(x)
        
        # first prepare the xy coordinates of the sets
        raw_data,_ = self._prepare_dat_2(plot_info)
                
        # add the xy coordinates of the vertical lines
        for l in labels:
            new_block = ["{}\t{}".format(l[0],y_min_lim) ]
            new_block.append( "{}\t{}".format(l[0],y_max_lim) )
            new_block.append("")
            raw_data += "\n".join(new_block)
        
        filexy_name = plot_info['filename']
        
        batch = []
        batch.append( 'READ XY "{}"'.format(filexy_name) )
        
        # axis limits
        batch.append("world {}, {}, {}, {}".format(x_min_lim,y_min_lim,x_max_lim,y_max_lim) )

        # axis label        
        batch.append( 'yaxis label "Dispersion"' )

        # axis ticks
        batch.append( 'xaxis  tick place both')
        batch.append( 'xaxis  tick spec type both')
        batch.append( 'xaxis  tick spec {}'.format(len(labels)))
        # set the name of the special points
        for i,l in enumerate(labels):
            batch.append( "xaxis  tick major {}, {}".format(i,l[0]) )
            batch.append( 'xaxis  ticklabel {}, "{}"'.format(i,l[1]) )

        # minor graphical tweak
        batch.append( "yaxis  tick minor ticks 3" )
        batch.append("frame linewidth 2.0")
        
        # use helvetica fonts
        batch.append( 'map font 4 to "Helvetica", "Helvetica"' )
        batch.append("yaxis  label font 4")
        batch.append("xaxis  label font 4")

        # set color and linewidths of bands
        for i in range(num_bands):
            batch.append( "s{} line color 1".format(i) )
            batch.append( "s{} linewidth 1".format(i) )

        # set color and linewidths of bands
        for i in range(num_bands,num_bands+num_labels):
            batch.append( "s{} line color 1".format(i) )
            batch.append( "s{} linewidth 2".format(i) )
        
        batch_data = "\n".join(batch) + "\n"
        extra_files = {"batch.dat":batch_data}
        
        return raw_data, extra_files


    def _prepare_dat_1(self,plot_info,**kwargs):
        """
        Write an N x M matrix. First column is the distance between kpoints,
        The other columns are the bands. Header contains number of kpoints and 
        the number of bands (commented).
        """
        if kwargs:
            raise TypeError("_prepare_dat_1 takes no keyword arguments")

        bands = plot_info['y']
        x = plot_info['x']
        
        return_text = []
        
        for i in zip(x,bands):
            line = [ "{:.8f}".format(i[0]) ] + [ "{:.8f}".format(j) for j in i[1] ]
            return_text.append( "\t".join( line ) )
        
        return "\n".join(return_text) + '\n', None
    
    def _prepare_dat_2(self,plot_info,**kwargs):
        """
        Format suitable for gnuplot using blocks.
        Columns with x and y (path and band energy). Several blocks, separated
        by two empty lines, one per energy band.
        """
        if kwargs:
            raise TypeError("_prepare_dat_2 takes no keyword arguments")
        
        bands = plot_info['y']
        x = plot_info['x']
        
        return_text = []
        
        the_bands = numpy.transpose(bands)
        
        for b in the_bands:
            for i in zip(x,b):
                line = [ "{:.8f}".format(i[0]) , "{:.8f}".format(i[1]) ]
                return_text.append( "\t".join( line ) )
            return_text.append("")
            return_text.append("")
        
        return "\n".join(return_text), None

    def _prepare_agr(self,plot_info,setnumber_offset=0,color_number=1,
                        legend="",title="",y_max_lim=None,y_min_lim=None,
                        y_origin=0.,**kwargs):
        """
        Prepare an xmgrace agr file
        :param plot_info: a dictionary
        :param setnumber_offset: an offset to be applied to all set numbers
        (i.e. s0 is replaced by s[offset], s1 by s[offset+1], etc.) 
        :param color_number: the color number for lines, symbols, error bars 
        and filling (should be less than the parameter max_num_agr_colors 
        defined below)
        :param legend: the legend (applied only to the first set)
        :param title: the title
        :param y_max_lim: the maximum on the y axis (if None, put the
            maximum of the bands)
        :param y_min_lim: the minimum on the y axis (if None, put the 
            minimum of the bands)
        :param y_origin: the new origin of the y axis -> all bands are replaced
            by bands-y_origin
        """
        if kwargs:
            raise TypeError("_prepare_agr got unexpected keyword argument(s) {}"
                            "".format(kwargs.keys()))

        import math
        # load the x and y of every set
        if color_number > max_num_agr_colors:
            raise ValueError("Color number is too high (should be less than {})"
                            "".format(max_num_agr_colors))
        
        bands = plot_info['y'] - y_origin
        x = plot_info['x']
        the_bands = numpy.transpose(bands)
        labels = plot_info['labels']
        num_labels = len(labels)

        # axis limits
        if y_max_lim is None:
            y_max_lim = the_bands.max()
        if y_min_lim is None:
            y_min_lim = the_bands.min()
        x_min_lim = min(x) # this isn't a numpy array, but a list
        x_max_lim = max(x)
        ytick_spacing = 10**int( math.log10( (y_max_lim - y_min_lim) ) )

        # prepare xticks labels
        sx1 = ""
        for i,l in enumerate(labels):
            sx1 += agr_single_xtick_template.substitute(index = i,
                                                     coord = l[0],
                                                     name = l[1],
                                                     )
        xticks = agr_xticks_template.substitute(num_labels = num_labels,
                                       single_xtick_templates = sx1,
                                       )

        # build the arrays with the xy coordinates
        all_sets = []
        for b in the_bands:
            this_set = ""
            for i in zip(x,b):
                line = "{:.8f}".format(i[0]) + '\t' + "{:.8f}".format(i[1]) +"\n"
                this_set += line
            all_sets.append(this_set)
        
        set_descriptions = ""
        for i,this_set in enumerate(all_sets):
            width = str(2.0) 
            set_descriptions += agr_set_description_template.substitute(
                                        set_number=i+setnumber_offset,
                                        linewidth = width,
                                        color_number = color_number,
                                        legend = legend if i==0 else ""
                                        )
        
        units = self.units
        
        graphs = agr_graph_template.substitute(x_min_lim=x_min_lim, 
                                               y_min_lim=y_min_lim,
                                               x_max_lim=x_max_lim,
                                               y_max_lim=y_max_lim,
                                               yaxislabel="Dispersion ({})".format(units),
                                               xticks_template=xticks,
                                               set_descriptions=set_descriptions,
                                               ytick_spacing=ytick_spacing,
                                               title=title,
                                               )
        sets = []
        for i,this_set in enumerate(all_sets):
            sets.append( agr_singleset_template.substitute(set_number = i+setnumber_offset,
                                                           xydata = this_set)
                         )
        the_sets = "&\n".join(sets)
        
        s = agr_template.substitute(graphs=graphs,sets=the_sets)
        
        return s,None
        
    def _prepare_json(self,plot_info,**kwargs):
        """
        Prepare a json file in a format compatible with the AiiDA band visualizer
        :param plot_info: a dictionary
        """
        import json
        
        if kwargs:
            raise TypeError("_prepare_json got unexpected keyword argument(s) {}"
                            "".format(kwargs.keys()))
        
        json_dict = {'label': self.label}

        bands = plot_info['y']
        labels = self.labels

        json_dict['path'] = []
        json_dict['paths'] = []

        try:
            _ = self.labels[1][1]
            for (position_from,label_from),(position_to,label_to) in zip(labels[:-1],labels[1:]):
                json_dict['path'].append([label_from,label_to])
                path_dict = {'length': position_to-position_from,
                             'from'  : label_from,
                             'to'    : label_to,
                             'values': bands[position_from:position_to+1,:].transpose().tolist(),
                             }
                json_dict['paths'].append(path_dict)
        except (TypeError,IndexError):
            label_from = "0"
            label_to = "1"
            path_dict = {'length': bands.shape[0]-1,
                         'from'  : label_from,
                         'to'    : label_to,
                         'values': bands.transpose().tolist(),
                         }
            json_dict['paths'].append(path_dict)
            json_dict['path'].append([label_from,label_to])
            
        return json.dumps(json_dict),None


max_num_agr_colors = 15

agr_template = Template(
"""
# Grace project file
#
@version 50122
@page size 792, 612
@page scroll 5%
@page inout 5%
@link page off
@map font 8 to "Courier", "Courier"
@map font 10 to "Courier-Bold", "Courier-Bold"
@map font 11 to "Courier-BoldOblique", "Courier-BoldOblique"
@map font 9 to "Courier-Oblique", "Courier-Oblique"
@map font 4 to "Helvetica", "Helvetica"
@map font 6 to "Helvetica-Bold", "Helvetica-Bold"
@map font 7 to "Helvetica-BoldOblique", "Helvetica-BoldOblique"
@map font 5 to "Helvetica-Oblique", "Helvetica-Oblique"
@map font 14 to "NimbusMonoL-BoldOblique", "NimbusMonoL-BoldOblique"
@map font 15 to "NimbusMonoL-Regular", "NimbusMonoL-Regular"
@map font 16 to "NimbusMonoL-RegularOblique", "NimbusMonoL-RegularOblique"
@map font 17 to "NimbusRomanNo9L-Medium", "NimbusRomanNo9L-Medium"
@map font 18 to "NimbusRomanNo9L-MediumItalic", "NimbusRomanNo9L-MediumItalic"
@map font 19 to "NimbusRomanNo9L-Regular", "NimbusRomanNo9L-Regular"
@map font 20 to "NimbusRomanNo9L-RegularItalic", "NimbusRomanNo9L-RegularItalic"
@map font 21 to "NimbusSansL-Bold", "NimbusSansL-Bold"
@map font 22 to "NimbusSansL-BoldCondensed", "NimbusSansL-BoldCondensed"
@map font 23 to "NimbusSansL-BoldCondensedItalic", "NimbusSansL-BoldCondensedItalic"
@map font 24 to "NimbusSansL-BoldItalic", "NimbusSansL-BoldItalic"
@map font 25 to "NimbusSansL-Regular", "NimbusSansL-Regular"
@map font 26 to "NimbusSansL-RegularCondensed", "NimbusSansL-RegularCondensed"
@map font 27 to "NimbusSansL-RegularCondensedItalic", "NimbusSansL-RegularCondensedItalic"
@map font 28 to "NimbusSansL-RegularItalic", "NimbusSansL-RegularItalic"
@map font 29 to "StandardSymbolsL-Regular", "StandardSymbolsL-Regular"
@map font 12 to "Symbol", "Symbol"
@map font 31 to "Symbol-Regular", "Symbol-Regular"
@map font 2 to "Times-Bold", "Times-Bold"
@map font 3 to "Times-BoldItalic", "Times-BoldItalic"
@map font 1 to "Times-Italic", "Times-Italic"
@map font 0 to "Times-Roman", "Times-Roman"
@map font 36 to "URWBookmanL-DemiBold", "URWBookmanL-DemiBold"
@map font 37 to "URWBookmanL-DemiBoldItalic", "URWBookmanL-DemiBoldItalic"
@map font 38 to "URWBookmanL-Light", "URWBookmanL-Light"
@map font 39 to "URWBookmanL-LightItalic", "URWBookmanL-LightItalic"
@map font 40 to "URWChanceryL-MediumItalic", "URWChanceryL-MediumItalic"
@map font 41 to "URWGothicL-Book", "URWGothicL-Book"
@map font 42 to "URWGothicL-BookOblique", "URWGothicL-BookOblique"
@map font 43 to "URWGothicL-Demi", "URWGothicL-Demi"
@map font 44 to "URWGothicL-DemiOblique", "URWGothicL-DemiOblique"
@map font 45 to "URWPalladioL-Bold", "URWPalladioL-Bold"
@map font 46 to "URWPalladioL-BoldItalic", "URWPalladioL-BoldItalic"
@map font 47 to "URWPalladioL-Italic", "URWPalladioL-Italic"
@map font 48 to "URWPalladioL-Roman", "URWPalladioL-Roman"
@map font 13 to "ZapfDingbats", "ZapfDingbats"
@map color 0 to (255, 255, 255), "white"
@map color 1 to (0, 0, 0), "black"
@map color 2 to (255, 0, 0), "red"
@map color 3 to (0, 255, 0), "green"
@map color 4 to (0, 0, 255), "blue"
@map color 5 to (255, 215, 0), "yellow"
@map color 6 to (188, 143, 143), "brown"
@map color 7 to (220, 220, 220), "grey"
@map color 8 to (148, 0, 211), "violet"
@map color 9 to (0, 255, 255), "cyan"
@map color 10 to (255, 0, 255), "magenta"
@map color 11 to (255, 165, 0), "orange"
@map color 12 to (114, 33, 188), "indigo"
@map color 13 to (103, 7, 72), "maroon"
@map color 14 to (64, 224, 208), "turquoise"
@map color 15 to (0, 139, 0), "green4"
@reference date 0
@date wrap off
@date wrap year 1950
@default linewidth 1.0
@default linestyle 1
@default color 1
@default pattern 1
@default font 0
@default char size 1.000000
@default symbol size 1.000000
@default sformat "%.8g"
@background color 0
@page background fill on
@timestamp off
@timestamp 0.03, 0.03
@timestamp color 1
@timestamp rot 0
@timestamp font 0
@timestamp char size 1.000000
@timestamp def "Wed Jul 30 16:44:34 2014"
@r0 off
@link r0 to g0
@r0 type above
@r0 linestyle 1
@r0 linewidth 1.0
@r0 color 1
@r0 line 0, 0, 0, 0
@r1 off
@link r1 to g0
@r1 type above
@r1 linestyle 1
@r1 linewidth 1.0
@r1 color 1
@r1 line 0, 0, 0, 0
@r2 off
@link r2 to g0
@r2 type above
@r2 linestyle 1
@r2 linewidth 1.0
@r2 color 1
@r2 line 0, 0, 0, 0
@r3 off
@link r3 to g0
@r3 type above
@r3 linestyle 1
@r3 linewidth 1.0
@r3 color 1
@r3 line 0, 0, 0, 0
@r4 off
@link r4 to g0
@r4 type above
@r4 linestyle 1
@r4 linewidth 1.0
@r4 color 1
@r4 line 0, 0, 0, 0
$graphs
$sets
"""
)

agr_xticks_template = Template(
"""
@    xaxis  tick spec $num_labels
$single_xtick_templates
""")

agr_single_xtick_template = Template(
"""
@    xaxis  tick major $index, $coord
@    xaxis  ticklabel $index, "$name"
""")

agr_graph_template = Template(
"""
@g0 on
@g0 hidden false
@g0 type XY
@g0 stacked false
@g0 bar hgap 0.000000
@g0 fixedpoint off
@g0 fixedpoint type 0
@g0 fixedpoint xy 0.000000, 0.000000
@g0 fixedpoint format general general
@g0 fixedpoint prec 6, 6
@with g0
@    world $x_min_lim, $y_min_lim, $x_max_lim, $y_max_lim
@    stack world 0, 0, 0, 0
@    znorm 1
@    view 0.150000, 0.150000, 1.150000, 0.850000
@    title "$title"
@    title font 0
@    title size 1.500000
@    title color 1
@    subtitle ""
@    subtitle font 0
@    subtitle size 1.000000
@    subtitle color 1
@    xaxes scale Normal
@    yaxes scale Normal
@    xaxes invert off
@    yaxes invert off
@    xaxis  on
@    xaxis  type zero false
@    xaxis  offset 0.000000 , 0.000000
@    xaxis  bar on
@    xaxis  bar color 1
@    xaxis  bar linestyle 1
@    xaxis  bar linewidth 1.0
@    xaxis  label ""
@    xaxis  label layout para
@    xaxis  label place auto
@    xaxis  label char size 1.000000
@    xaxis  label font 4
@    xaxis  label color 1
@    xaxis  label place normal
@    xaxis  tick on
@    xaxis  tick major 5
@    xaxis  tick minor ticks 0
@    xaxis  tick default 6
@    xaxis  tick place rounded true
@    xaxis  tick in
@    xaxis  tick major size 1.000000
@    xaxis  tick major color 1
@    xaxis  tick major linewidth 1.0
@    xaxis  tick major linestyle 1
@    xaxis  tick major grid on
@    xaxis  tick minor color 1
@    xaxis  tick minor linewidth 1.0
@    xaxis  tick minor linestyle 1
@    xaxis  tick minor grid off
@    xaxis  tick minor size 0.500000
@    xaxis  ticklabel on
@    xaxis  ticklabel format general
@    xaxis  ticklabel prec 5
@    xaxis  ticklabel formula ""
@    xaxis  ticklabel append ""
@    xaxis  ticklabel prepend ""
@    xaxis  ticklabel angle 0
@    xaxis  ticklabel skip 0
@    xaxis  ticklabel stagger 0
@    xaxis  ticklabel place normal
@    xaxis  ticklabel offset auto
@    xaxis  ticklabel offset 0.000000 , 0.010000
@    xaxis  ticklabel start type auto
@    xaxis  ticklabel start 0.000000
@    xaxis  ticklabel stop type auto
@    xaxis  ticklabel stop 0.000000
@    xaxis  ticklabel char size 1.500000
@    xaxis  ticklabel font 4
@    xaxis  ticklabel color 1
@    xaxis  tick place both
@    xaxis  tick spec type both
$xticks_template
@    yaxis  on
@    yaxis  type zero false
@    yaxis  offset 0.000000 , 0.000000
@    yaxis  bar on
@    yaxis  bar color 1
@    yaxis  bar linestyle 1
@    yaxis  bar linewidth 1.0
@    yaxis  label "$yaxislabel"
@    yaxis  label layout para
@    yaxis  label place auto
@    yaxis  label char size 1.500000
@    yaxis  label font 4
@    yaxis  label color 1
@    yaxis  label place normal
@    yaxis  tick on
@    yaxis  tick major $ytick_spacing
@    yaxis  tick minor ticks 1
@    yaxis  tick default 6
@    yaxis  tick place rounded true
@    yaxis  tick in
@    yaxis  tick major size 1.000000
@    yaxis  tick major color 1
@    yaxis  tick major linewidth 1.0
@    yaxis  tick major linestyle 1
@    yaxis  tick major grid off
@    yaxis  tick minor color 1
@    yaxis  tick minor linewidth 1.0
@    yaxis  tick minor linestyle 1
@    yaxis  tick minor grid off
@    yaxis  tick minor size 0.500000
@    yaxis  ticklabel on
@    yaxis  ticklabel format general
@    yaxis  ticklabel prec 5
@    yaxis  ticklabel formula ""
@    yaxis  ticklabel append ""
@    yaxis  ticklabel prepend ""
@    yaxis  ticklabel angle 0
@    yaxis  ticklabel skip 0
@    yaxis  ticklabel stagger 0
@    yaxis  ticklabel place normal
@    yaxis  ticklabel offset auto
@    yaxis  ticklabel offset 0.000000 , 0.010000
@    yaxis  ticklabel start type auto
@    yaxis  ticklabel start 0.000000
@    yaxis  ticklabel stop type auto
@    yaxis  ticklabel stop 0.000000
@    yaxis  ticklabel char size 1.250000
@    yaxis  ticklabel font 4
@    yaxis  ticklabel color 1
@    yaxis  tick place both
@    yaxis  tick spec type none
@    altxaxis  off
@    altyaxis  off
@    legend on
@    legend loctype view
@    legend 0.85, 0.8
@    legend box color 1
@    legend box pattern 1
@    legend box linewidth 1.0
@    legend box linestyle 1
@    legend box fill color 0
@    legend box fill pattern 1
@    legend font 0
@    legend char size 1.000000
@    legend color 1
@    legend length 4
@    legend vgap 1
@    legend hgap 1
@    legend invert false
@    frame type 0
@    frame linestyle 1
@    frame linewidth 1.0
@    frame color 1
@    frame pattern 1
@    frame background color 0
@    frame background pattern 0
$set_descriptions
"""
)

agr_set_description_template = Template(
"""
@    s$set_number hidden false
@    s$set_number type xy
@    s$set_number symbol 0
@    s$set_number symbol size 1.000000
@    s$set_number symbol color $color_number
@    s$set_number symbol pattern 1
@    s$set_number symbol fill color $color_number
@    s$set_number symbol fill pattern 0
@    s$set_number symbol linewidth 1.0
@    s$set_number symbol linestyle 1
@    s$set_number symbol char 65
@    s$set_number symbol char font 0
@    s$set_number symbol skip 0
@    s$set_number line type 1
@    s$set_number line linestyle 1
@    s$set_number line linewidth $linewidth
@    s$set_number line color $color_number
@    s$set_number line pattern 1
@    s$set_number baseline type 0
@    s$set_number baseline off
@    s$set_number dropline off
@    s$set_number fill type 0
@    s$set_number fill rule 0
@    s$set_number fill color $color_number
@    s$set_number fill pattern 1
@    s$set_number avalue off
@    s$set_number avalue type 2
@    s$set_number avalue char size 1.000000
@    s$set_number avalue font 0
@    s$set_number avalue color 1
@    s$set_number avalue rot 0
@    s$set_number avalue format general
@    s$set_number avalue prec 3
@    s$set_number avalue prepend ""
@    s$set_number avalue append ""
@    s$set_number avalue offset 0.000000 , 0.000000
@    s$set_number errorbar on
@    s$set_number errorbar place both
@    s$set_number errorbar color $color_number
@    s$set_number errorbar pattern 1
@    s$set_number errorbar size 1.000000
@    s$set_number errorbar linewidth 1.0
@    s$set_number errorbar linestyle 1
@    s$set_number errorbar riser linewidth 1.0
@    s$set_number errorbar riser linestyle 1
@    s$set_number errorbar riser clip off
@    s$set_number errorbar riser clip length 0.100000
@    s$set_number comment "Cols 1:2"
@    s$set_number legend "$legend"
"""
)

agr_singleset_template = Template(
"""
@target G0.S$set_number
@type xy
$xydata
""")




        