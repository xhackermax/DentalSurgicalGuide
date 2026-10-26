"""Numerical Surface Nets helpers, imported only by the smoothing worker.
No label changes, morphology, inflation or subdivision. VTK box uses full width.
"""
import numpy as np
import vtk
from scipy import ndimage,sparse
from scipy.spatial import cKDTree
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray,vtk_to_numpy
def image(a):
    img=vtk.vtkImageData();img.SetDimensions(*a.shape[::-1]);img.SetSpacing(1,1,1)
    img.GetPointData().SetScalars(numpy_to_vtk(np.ascontiguousarray(a).ravel(),deep=True))
    return img

def surface_nets(a,labels,half=.45,relax=.2,iterations=16,automatic=False,greedy=False):
    sn=vtk.vtkSurfaceNets3D();sn.SetInputData(image(a));sn.SetNumberOfLabels(len(labels))
    for i,label in enumerate(labels):sn.SetLabel(i,int(label))
    sn.SetBackgroundLabel(0);sn.SetOutputMeshTypeToTriangles()
    if greedy:sn.SetTriangulationStrategyToGreedy()
    else:sn.SetTriangulationStrategyToMinEdge()
    sn.SetSmoothing(iterations>0);sn.SetAutomaticSmoothingConstraints(automatic)
    sn.SetConstraintStrategyToConstraintBox();sn.SetConstraintBox(2*half,2*half,2*half)
    sn.SetNumberOfIterations(iterations);sn.SetRelaxationFactor(relax)
    sn.Update();out=vtk.vtkPolyData();out.DeepCopy(sn.GetOutput());return out

def arrays(pd):
    return (vtk_to_numpy(pd.GetPoints().GetData()).astype(float),
            vtk_to_numpy(pd.GetPolys().GetConnectivityArray()).reshape(-1,3).astype(np.int64))

def poly(v,f):
    p=vtk.vtkPolyData();points=vtk.vtkPoints();points.SetData(numpy_to_vtk(np.ascontiguousarray(v,dtype=float),deep=True));p.SetPoints(points)
    cells=vtk.vtkCellArray();cells.SetData(numpy_to_vtkIdTypeArray(np.arange(0,3*len(f)+1,3,dtype=np.int64),deep=True),numpy_to_vtkIdTypeArray(np.ascontiguousarray(f,dtype=np.int64).ravel(),deep=True));p.SetPolys(cells);return p

def split_manual(pd,label):
    v,f=arrays(pd);bl=vtk_to_numpy(pd.GetCellData().GetArray('BoundaryLabels'))
    keep=(bl[:,0]==label)|(bl[:,1]==label);faces=f[keep].copy();flip=bl[keep,1]==label
    faces[flip]=faces[flip,::-1];used,inv=np.unique(faces,return_inverse=True)
    return poly(v[used],inv.reshape(-1,3)),used

def split_atlas(pd,labels):
    if not hasattr(vtk,'vtkSurfaceNetsAtlas'):return {int(k):split_manual(pd,k)[0] for k in labels},'BOUNDARY_LABELS'
    a=vtk.vtkSurfaceNetsAtlas();a.SetInputDataObject(pd);a.SetBackgroundLabel(0)
    a.SetExtractionModeToLabelSet();a.SetOutputStyleToAll();a.GenerateRegionsOn();a.GeneratePatchesOff();a.ResolveNonManifoldPointsOn()
    for k in labels:a.AddSelectedLabel(int(k))
    a.Update();out=a.GetOutput();parts={}
    for i in range(out.GetNumberOfPartitionedDataSets()):
        pd_=out.GetPartitionedDataSet(i).GetPartition(0)
        if pd_ is None or not pd_.GetNumberOfCells():continue
        k=int(pd_.GetCellData().GetArray('Label').GetTuple1(0));clone=vtk.vtkPolyData();clone.DeepCopy(pd_);parts[k]=clone
    return parts,'ATLAS'

def volume(v,f):
    q=v-v.mean(axis=0);t=q[f];return float(np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()/6)

def topology(v,f):
    edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
    _,counts=np.unique(edges,axis=0,return_counts=True)
    graph=sparse.csr_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(v),len(v)))
    return dict(closed=bool(np.all(counts==2)),bad_edges=int(np.count_nonzero(counts!=2)),components=int(sparse.csgraph.connected_components(graph,directed=False)[0]))

def boundary_samples(mask):
    cross=ndimage.generate_binary_structure(3,1)
    inside=mask & ~ndimage.binary_erosion(mask,structure=cross,border_value=0)
    outside=ndimage.binary_dilation(inside,structure=cross)&~mask
    coords=np.argwhere(inside|outside);return coords[:,::-1].astype(float),mask[tuple(coords.T)]

def consistency(pd,points,expected):
    v,_=arrays(pd);pts=vtk.vtkPolyData();p=vtk.vtkPoints();p.SetData(numpy_to_vtk(points,deep=True));pts.SetPoints(p)
    s=vtk.vtkSelectEnclosedPoints();s.SetInputData(pts);s.SetSurfaceData(pd);s.CheckSurfaceOn()
    diagonal=float(np.linalg.norm(np.ptp(v,axis=0)));s.SetTolerance(1e-4/max(diagonal,1e-20));s.Update()
    predicted=vtk_to_numpy(s.GetOutput().GetPointData().GetArray('SelectedPoints')).astype(bool)
    return dict(boundary_points_tested=len(points),consistent=int(np.count_nonzero(predicted==expected)),
                occupancy_consistency=float(np.mean(predicted==expected)),inside_to_outside=int(np.count_nonzero(expected&~predicted)),outside_to_inside=int(np.count_nonzero(~expected&predicted)))

def geometry(v,f):
    t=v[f];cross=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);length=np.linalg.norm(cross,axis=1)
    return cross/np.maximum(length[:,None],1e-20),length*.5,t.mean(axis=1)

def roughness_radius(v,f,radius):
    n,area,centres=geometry(v,f);tree=cKDTree(centres)
    # Bound memory while computing the exact physical-radius neighborhood.
    accum=0.
    for start in range(0,len(f),2048):
        neighborhoods=tree.query_ball_point(centres[start:start+2048],radius)
        lengths=np.array([len(x) for x in neighborhoods]);cols=np.concatenate(neighborhoods);rows=np.repeat(np.arange(len(lengths)),lengths)
        B=sparse.csr_matrix((area[cols],(rows,cols)),shape=(len(lengths),len(f)))
        avg=B@n;avg/=np.maximum(np.linalg.norm(avg,axis=1)[:,None],1e-20)
        accum+=float(np.dot(area[start:start+len(lengths)],1-np.einsum('ij,ij->i',n[start:start+len(lengths)],avg)))
    return accum/float(area.sum())

def sampled_distance(a,b):
    d=vtk.vtkDistancePolyDataFilter();d.SetInputData(0,a);d.SetInputData(1,b);d.SignedDistanceOff();d.ComputeSecondDistanceOn();d.Update()
    return max(float(np.max(np.abs(vtk_to_numpy(o.GetPointData().GetArray('Distance'))))) for o in (d.GetOutput(),d.GetSecondDistanceOutput()))
