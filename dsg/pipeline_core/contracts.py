from dataclasses import dataclass
import re
import numpy as np

class DSGError(Exception):
    def __init__(self,stage,reason,**context):
        super().__init__(f'[{stage}] {reason}')
        self.stage=stage;self.reason=reason;self.context=context

class ContractError(DSGError,ValueError):pass
class InputError(DSGError):pass
class EngineError(DSGError):pass
class MeshingError(DSGError):pass

VALID_COMPAT=frozenset(range(33))|{53,54,55}
SCHEMA_VERSION=1

def _geometry(dims,spacing):
    if len(dims)!=3 or any(not isinstance(v,(int,np.integer)) or v<=0 for v in dims):
        raise ContractError('input','dimensiones inválidas')
    if len(spacing)!=3 or not all(np.isfinite(v) and v>0 for v in spacing):
        raise ContractError('input','spacing inválido')
    return tuple(int(v) for v in dims),tuple(float(v) for v in spacing)

@dataclass(frozen=True)
class VolumeInput:
    data:np.ndarray
    slopes:np.ndarray
    intercepts:np.ndarray
    dims:tuple
    spacing_zyx:tuple
    units:str='STORED_CALIBRATED'
    @classmethod
    def parse(cls,data,slopes,intercepts,dims,spacing):
        dims,spacing=_geometry(dims,spacing)
        if data.ndim!=3 or data.shape!=dims or data.dtype.kind not in 'iuf':
            raise ContractError('input','volumen incompatible con sus dimensiones')
        if data.dtype.kind=='f' and not np.isfinite(data).all():raise ContractError('input','volumen con intensidades no finitas')
        for values in (slopes,intercepts):
            if values.shape!=(dims[0],) or not np.isfinite(values).all():
                raise ContractError('input','calibración incompatible con las capas')
        if not np.all(slopes!=0):raise ContractError('input','escala de calibración nula')
        return cls(data,slopes,intercepts,dims,spacing)

def compat_to_fdi(label):
    if 1<=label<=8:return 19-label
    if 9<=label<=16:return label+12
    if 17<=label<=24:return 55-label
    if 25<=label<=32:return label+16
    return None

@dataclass(frozen=True)
class Labelmap:
    data:np.ndarray
    dims:tuple
    spacing_zyx:tuple
    engine:str
    counts:dict
    fdis:frozenset
    @classmethod
    def parse(cls,data,dims,spacing,engine):
        dims,spacing=_geometry(dims,spacing)
        if data.shape!=dims or data.ndim!=3:raise ContractError('labelmap','dimensiones distintas del CBCT')
        if data.dtype not in (np.dtype('uint8'),np.dtype('uint16')):raise ContractError('labelmap','dtype inválido')
        labels,counts=np.unique(data,return_counts=True)
        values=set(int(v) for v in labels)
        if values-VALID_COMPAT:raise ContractError('labelmap','etiquetas fuera del contrato DSG',labels=sorted(values-VALID_COMPAT))
        fdis=frozenset(compat_to_fdi(v) for v in values if 1<=v<=32)
        if not fdis:raise ContractError('labelmap','no produjo dientes individualizados')
        return cls(data,dims,spacing,str(engine),{int(k):int(v) for k,v in zip(labels,counts)},fdis)
    def summary(self):
        return {'dims_zyx':list(self.dims),'spacing_zyx':list(self.spacing_zyx),
                'dtype':str(self.data.dtype),'labels':sorted(self.counts),'fdis':sorted(self.fdis),
                'voxels':{str(k):v for k,v in self.counts.items()}}

@dataclass(frozen=True)
class ResultManifest:
    payload:dict
    @classmethod
    def parse(cls,payload,expected_run_id=None):
        if payload.get('schema_version')!=SCHEMA_VERSION:raise ContractError('manifest','versión incompatible; vuelve a ejecutar la segmentación')
        run_id=payload.get('run_id','')
        if not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',run_id):raise ContractError('manifest','run_id inválido')
        if expected_run_id and run_id!=expected_run_id:raise ContractError('manifest','resultado de otra ejecución')
        if payload.get('status') not in ('OK','ERROR'):raise ContractError('manifest','estado inválido')
        if payload['status']=='OK':
            contract=payload.get('labelmap_contract')
            if not isinstance(contract,dict):raise ContractError('manifest','falta el contrato del labelmap')
            dims=contract.get('dims_zyx',[]);labels=contract.get('labels',[])
            if len(dims)!=3 or any(type(v)!=int or v<=0 for v in dims):raise ContractError('manifest','dimensiones inválidas')
            if contract.get('dtype') not in ('uint8','uint16') or not labels or any(type(v)!=int or v not in VALID_COMPAT for v in labels):raise ContractError('manifest','labels o dtype inválidos')
            if not any(1<=v<=32 for v in labels):raise ContractError('manifest','no produjo dientes individualizados')
            if not isinstance(payload.get('normalized_labels_path'),str) or not payload['normalized_labels_path']:raise ContractError('manifest','falta el archivo de labels')
        return cls(payload)
