from __future__ import print_function

import sys
import ctypes
import numpy
from numpy.linalg import norm


import bridge

surf_id_to_handle = {}
surf_handle_to_id = {}
vol_id_to_handle = {}
vol_handle_to_id = {}

def versions():
    """Return a (str,int) tuple: the version and SVN revision of the active DagMC C++ library"""
    return ('{0:.4}'.format(bridge.lib.dag_version()), int(bridge.lib.dag_rev_version()))

def load( filename ):
    """Load a given filename into DagMC"""
    global surf_id_to_handle, surf_handle_to_id, vol_id_to_handle, vol_handle_to_id
    bridge.lib.dag_load( filename )

    def get_geom_list( dim ):
        
        count = ctypes.c_int(0)
        
        list_p = bridge.lib.geom_id_list( dim, ctypes.byref(count) )

        r_dict_forward = {}
        for i in range(0,count.value):
            eh = bridge.lib.handle_from_id( dim, list_p[i] ).value 
            if eh == 0:
                raise bridge.DagmcError(
                        '{0} ID {1} has no entity handle'.format(
                         {2:'surf',3:'vol'}[dim], list_p[i]))
            else:
                r_dict_forward[ list_p[i] ] = eh

        r_dict_backward = dict((v,k) for k,v in r_dict_forward.iteritems() )
        
        return r_dict_forward, r_dict_backward

    surf_id_to_handle, surf_handle_to_id = get_geom_list( 2 )
    vol_id_to_handle, vol_handle_to_id  = get_geom_list( 3 )

def get_surface_list( ):
    """return a list of valid surface IDs"""
    return surf_id_to_handle.keys()

def get_volume_list( ):
    """return a list of valid volume IDs"""
    return vol_id_to_handle.keys()

def volume_is_graveyard( vol_id ):
    """True if the given volume id is a graveyard volume"""
    eh = vol_id_to_handle[ vol_id ]
    result = bridge.lib.vol_is_graveyard( eh )
    return (result != 0)

def volume_is_implicit_complement( vol_id ):
    """True if the given volume id is the implicit complement volume"""
    eh = vol_id_to_handle[ vol_id ]
    result = bridge.lib.vol_is_implicit_complement( eh )
    return (result != 0)

def volume_metadata( vol_id ):
    """Get the metadata of the given volume id

    returns a dictionary containing keys 'material', 'rho', and 'imp', corresponding
    to the DagmcVolData struct in DagMC.hpp

    """
    eh = vol_id_to_handle[ vol_id ]
    mat = ctypes.c_int()
    rho = ctypes.c_double()
    imp = ctypes.c_double()

    bridge.lib.get_volume_metadata( eh, mat, rho, imp )

    return {'material':mat.value, 'rho':rho.value, 'imp':imp.value}

def point_in_volume( vol_id, xyz, uvw = [0,0,0] ):
    """Determine whether the given point, xyz, is in the given volume.
    
    If provided, uvw is used to determine the ray fire direction for the underlying 
    query.  Otherwise, a random direction will be chosen. 

    
    """
    xyz = numpy.array( xyz, dtype=numpy.float64 )
    uvw = numpy.array( uvw, dtype=numpy.float64 )

    eh = vol_id_to_handle[ vol_id ]
    result = ctypes.c_int(-2)

    bridge.lib.dag_pt_in_vol( eh, xyz, ctypes.byref(result), uvw, None )

    return (result.value == 1)

def find_volume( xyz, uvw = [1,0,0] ):
    """Determine which volume the given point is in.

    Return a volume id.  If no volume contains the point, a DagmcError may be raised,
    or the point may be reported to be part of the implicit complement.

    This function may be slow if many volumes exist.

    """

    xyz = numpy.array( xyz, dtype=numpy.float64 )
    uvw = numpy.array( uvw, dtype=numpy.float64 )

    for eh, vol_id in vol_handle_to_id.iteritems():
        result = ctypes.c_int(-2)
        bridge.lib.dag_pt_in_vol( eh, xyz, ctypes.byref(result), uvw, None )
        if result.value == 1:
            return vol_id
    
    raise bridge.DagmcError("The point {0} does not appear to be in any volume".format(xyz) )
    

def fire_one_ray( vol_id, xyz, uvw ):
    """Fire a ray from xyz, in the direction uvw, at the specified volume

    uvw must represent a unit vector.

    Only intersections that *exit* the volume will be detected.  Entrance intersections
    are not detected.  In most cases, you should only 
    call this function with arguments for which point_in_volume would return True.

    Returns a (surface id, distance) tuple, or None if no intersection detected.

    If a ray in a given direction will traverse several volumes in a row, ray_iterator should
    be used instead.
    """
    xyz = numpy.array( xyz, dtype=numpy.float64 )
    uvw = numpy.array( uvw, dtype=numpy.float64 )

    eh = vol_id_to_handle[ vol_id ]
    
    surf_result = bridge.EntityHandle( 0 )
    dist_result = ctypes.c_double(0.0)

    bridge.lib.dag_ray_fire( eh, xyz, uvw, 
                             ctypes.byref( surf_result ), ctypes.byref( dist_result ),
                             None, 0.0 )


    if( surf_result.value != 0 ):
        return ( surf_handle_to_id[ surf_result.value ], dist_result.value )
    else:
        return None

def ray_iterator( init_vol_id, startpoint, direction, **kw ):
    """Return an iterator for a ray in a single direction.

    The iterator will yield a series of tuples (vol,dist,surf), indicating the next
    volume intersected, the distance to the next intersection (from the last intersection),
    and the surface intersected.  Stops iterating when no further intersections are 
    detected along the ray.  This is the only way to traverse volumes along a given ray.

    Keyword arguments:
    yield_xyz: results will contain a fourth tuple element, being the xyz position of the 
               intersection
    """

    eh = bridge.EntityHandle( vol_id_to_handle[ init_vol_id ] )
    xyz = numpy.array( startpoint, dtype=numpy.float64 )
    uvw = numpy.array( direction, dtype=numpy.float64 )

    with bridge._ray_history() as history:
        
        surf = bridge.EntityHandle( 0 )
        dist_result = ctypes.c_double( 0.0 )
        while eh != 0:

            bridge.lib.dag_ray_fire( eh, xyz, uvw, 
                                     ctypes.byref(surf), ctypes.byref(dist_result),
                                     history, 0.0 )

            if surf.value == 0:
                break

            # set eh to the new volume
            bridge.lib.dag_next_vol( surf, eh, ctypes.byref(eh) )
            xyz += uvw * dist_result.value

            newvol = vol_handle_to_id[eh.value]
            dist = dist_result.value
            newsurf = surf_handle_to_id[ surf.value ]
            
            if kw.get( 'yield_xyz', False ) :
                yield ( newvol, dist, newsurf, xyz )
            else: 
                yield ( newvol, dist, newsurf )


def tell_ray_story( startpoint, direction, output = sys.stdout ):
    """Write a human-readable history of a ray in a given direction.

    The history of the ray from startpoint in direction is written to the given output file.
    The initial volume in which startpoint resides will be determined, and 
    the direction argument will be normalized to a unit vector.

    """
    xyz = numpy.array( startpoint, dtype = numpy.float64 )
    uvw = numpy.array( direction, dtype = numpy.float64 ) 
    uvw /= norm(uvw)

    def pr( *args ): 
        print( *args, file = output )

    def vol_notes( v ):
        notes = []
        md = volume_metadata( v )
        if md['material'] == 0:
            notes.append( 'void' )
        else:
            notes.append( 'mat='+str( md['material'] ) )
            notes.append( 'rho='+str( md['rho'] ) )
        if volume_is_graveyard( v ): 
            notes.append( 'graveyard' )
        if volume_is_implicit_complement( v ):
            notes.append( 'implicit complement' )
        return '({0})'.format( ', '.join(notes) )

    pr( 'Starting a ray at',xyz,'in the direction',uvw )

    first_volume = find_volume( xyz, uvw )
    
    pr( 'The ray starts in volume', first_volume, vol_notes(first_volume) )

    for (vol, dist, surf, xyz) in ray_iterator( first_volume, xyz, uvw, yield_xyz = True ):

        pr( '  next intersection at distance',dist,'on surface',surf )
        pr( '  new xyz =', xyz )
        pr( 'proceeding into volume', vol, vol_notes(vol) )

    pr( 'No more intersections' )

