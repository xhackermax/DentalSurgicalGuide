"""Positive volume attachment receipts from a strict common interior witness."""
import math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def _closed(vertices,faces):
    vertices=np.asarray(vertices,dtype=float);faces=np.asarray(faces,dtype=np.int64)
    if vertices.ndim!=2 or vertices.shape[1]!=3 or faces.ndim!=2 or faces.shape[1]!=3 or not len(faces) or not np.isfinite(vertices).all():
        raise ValueError('SLEEVE_ATTACHMENT_INVALID_MESH')
    if faces.min()<0 or faces.max()>=len(vertices):raise ValueError('SLEEVE_ATTACHMENT_INVALID_INDEX')
    edges=np.sort(np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]])),axis=1)
    _,counts=np.unique(edges,axis=0,return_counts=True)
    if np.any(counts!=2):raise ValueError('SLEEVE_ATTACHMENT_OPEN_MESH')
    triangles=vertices[faces]
    if np.any(np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1)<1.e-12):
        raise ValueError('SLEEVE_ATTACHMENT_DEGENERATE_MESH')
    return vertices,faces,triangles,BVHTree.FromPolygons(vertices.tolist(),faces.tolist(),all_triangles=True)


def _winding(point,triangles):
    a,b,c=(triangles[:,i]-point for i in range(3))
    la,lb,lc=(np.linalg.norm(x,axis=1) for x in (a,b,c))
    numerator=np.einsum('ij,ij->i',a,np.cross(b,c))
    denominator=la*lb*lc+np.einsum('ij,ij->i',a,b)*lc+np.einsum('ij,ij->i',b,c)*la+np.einsum('ij,ij->i',c,a)*lb
    return float(np.sum(2.*np.arctan2(numerator,denominator))/(4.*math.pi))


def _segment_triangle(start,end,triangle):
    direction=end-start;edge1=triangle[1]-triangle[0];edge2=triangle[2]-triangle[0]
    h=np.cross(direction,edge2);det=float(np.dot(edge1,h))
    if abs(det)<1.e-12:return None
    s=start-triangle[0];u=float(np.dot(s,h)/det)
    if u < -1.e-8 or u > 1.+1.e-8:return None
    q=np.cross(s,edge1);v=float(np.dot(direction,q)/det);t=float(np.dot(edge2,q)/det)
    if v < -1.e-8 or u+v > 1.+1.e-8 or t < -1.e-8 or t > 1.+1.e-8:return None
    return start+t*direction


def certify_sleeve_attachment(primary_vertices,primary_faces,sleeve_vertices,sleeve_faces,min_overlap_mm=.01,*,near_point_mm=None,maximum_witness_distance_mm=None):
    """Return a strict common-interior witness, or reject uncertain attachment.

    A point inside both closed meshes with positive distance to each boundary
    certifies a positive common volume. This does not assess strength or lumen
    clearance. Inputs must be final triangulated geometry in world millimetres.
    The search is conservative: failure to find a witness rejects the candidate.
    """
    clearance=float(min_overlap_mm)
    if not math.isfinite(clearance) or clearance<=0:raise ValueError('SLEEVE_ATTACHMENT_INVALID_TOLERANCE')
    va,fa,ta,a=_closed(primary_vertices,primary_faces)
    vb,fb,tb,b=_closed(sleeve_vertices,sleeve_faces)
    tested=0
    def receipt(point):
        nonlocal tested
        tested+=1;point=np.asarray(point,float)
        if near_point_mm is not None and (maximum_witness_distance_mm is None or np.linalg.norm(point-np.asarray(near_point_mm,float))>float(maximum_witness_distance_mm)):return None
        na=a.find_nearest(Vector(point));nb=b.find_nearest(Vector(point))
        if na[0] is None or nb[0] is None or min(na[3],nb[3])<clearance:return None
        wa=_winding(point,ta)
        if abs(abs(wa)-1.)>1.e-4:return None
        wb=_winding(point,tb)
        if abs(abs(wb)-1.)>1.e-4:return None
        common=float(min(na[3],nb[3]))
        return {'valid':True,'positive_volume_overlap':True,'witness_mm':point.tolist(),
                'primary_clearance_mm':float(na[3]),'sleeve_clearance_mm':float(nb[3]),
                'primary_winding':wa,'sleeve_winding':wb,'minimum_required_clearance_mm':clearance,
                'common_interior_ball_radius_mm':common,'common_volume_lower_bound_mm3':4.*math.pi*common**3/3.,
                'witnesses_tested':tested,'method':'STRICT_INTERIOR_WINDING_AND_BOUNDARY_DISTANCE'}
    overlaps=a.overlap(b)
    for ia,ib in overlaps:
        first,second=ta[ia],tb[ib];points=[]
        for tri,other in ((first,second),(second,first)):
            for i in range(3):
                hit=_segment_triangle(tri[i],tri[(i+1)%3],other)
                if hit is not None:points.append(hit)
        if not points:continue
        center=np.mean(points,axis=0)
        normals=[]
        for triangle in (first,second):
            normal=np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0]);normal/=np.linalg.norm(normal)
            normals.append(normal)
        direction=normals[0]+normals[1];length=np.linalg.norm(direction)
        if length<1.e-8:continue
        direction/=length
        # Test both orientations so inward-oriented but consistent closed meshes work.
        for distance in (clearance*2.,clearance*4.,clearance*8.,clearance*16.,clearance*32.):
            for sign in (-1.,1.):
                result=receipt(center+sign*distance*direction)
                if result:return result
    # Containment without crossing boundaries: sampled face centers moved inward.
    for triangles in (ta,tb):
        step=max(1,len(triangles)//1024)
        for triangle in triangles[::step]:
            center=triangle.mean(axis=0);normal=np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0]);normal/=np.linalg.norm(normal)
            for sign in (-1.,1.):
                result=receipt(center+sign*clearance*2.*normal)
                if result:return result
    raise ValueError('SLEEVE_ATTACHMENT_NO_POSITIVE_VOLUME_WITNESS:'+str(tested))
