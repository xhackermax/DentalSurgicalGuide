"""Built-in nominal size libraries; these are not manufacturer CAD geometries.

* BTI: every implant reference listed in the official BTI Store (10 platforms,
  Interna and Externa), decoded from the reference code and cross-checked with
  the product name.  See ``resources/implant_catalogues/bti_store_2026_10.json``.
* Klockner VEGA/VEGA+, MIS SEVEN/C1 and Astra Tech EV/Profile EV: manufacturer
  catalogues, see ``resources/implant_catalogues/other_brands_2026_10.json``.
* Straumann Standard Plus: reference table from the manufacturer catalog;
  the original user matrix is retained unchanged as a historical source.

Each size is represented by DSG's nominal body envelope: a circumscribed
cylinder of the nominal diameter and length, platform at its coronal end.  The
DSG implant mesh of the same size lies inside that envelope, so a size that is
admissible for the envelope is conservative for the DSG implant.
"""
import json,math
from functools import lru_cache
from pathlib import Path
import numpy as np

FOLDER=Path(__file__).parent/'resources/implant_catalogues'
BTI_PATH=FOLDER/'bti_store_2026_10.json'
OTHER_PATH=FOLDER/'other_brands_2026_10.json'
USER_PATH=FOLDER/'dimensions_bti_straumann.json'
PATH=BTI_PATH  # backwards-compatible name
NOMINAL_PATHS=(BTI_PATH,OTHER_PATH)
USER_KEYS=('STRAUMANN_SP',)

@lru_cache(maxsize=None)
def _load(path):
    return json.loads(Path(path).read_text('utf-8'))

def _nominal():
    """key -> (file data, catalogue entry) for every reference-based library."""
    out={}
    for path in NOMINAL_PATHS:
        data=_load(str(path))
        for key,entry in data['catalogues'].items():
            if key in out:raise ValueError('Biblioteca duplicada: '+key)
            out[key]=(data,entry)
    return out

def _libraries():
    items=[]
    for key,(data,entry) in _nominal().items():
        ds=sorted({i['diameter_mm'] for i in entry['items']})
        where=f"plataforma Ø{entry['platform_mm']:g}" if 'platform_mm' in entry else entry.get('brand','')
        items.append((key,entry['family'],f"{entry['connection']} · {where} · Ø {ds[0]:g}–{ds[-1]:g} mm · {len(entry['items'])} referencias"))
    user=_load(str(USER_PATH))['catalogues']
    for key in USER_KEYS:
        if key in user and key not in _nominal():items.append((key,user[key]['family'],'Medidas de la matriz aportada'))
    items.append(('CUSTOM','Catálogo con mallas reales','Catálogo externo de geometría'))
    return tuple(items)

LIBRARIES=_libraries()

def signature_paths():
    return NOMINAL_PATHS+(USER_PATH,)

def rows(key):
    nominal=_nominal()
    if key in nominal:
        data,entry=nominal[key];result=[]
        source=entry.get('source') or data.get('source','')
        for item in entry['items']:
            if item.get('availability','LISTED')!='LISTED':continue
            d,l=float(item['diameter_mm']),float(item['length_mm'])
            result.append(dict(item,id=f"{key}:{item['ref']}",family=entry['family'],diameter_mm=d,length_mm=l,platform_local_mm=[0,0,l/2],
                dimension_only=True,source_cell=item['ref'],reference=f"{source} · {item['ref']} · {data['retrieved']}",
                platform_reference='NOMINAL_ENDOSSEOUS_BODY_TOP'))
        return result
    user=_load(str(USER_PATH))
    if key not in USER_KEYS or key not in user['catalogues']:raise ValueError('Biblioteca desconocida.')
    entry=user['catalogues'][key];result=[]
    for item in entry['items']:
        if item['availability']!='LISTED':continue
        d,l=item['diameter_mm'],item['length_mm']
        result.append(dict(item,id=f'{key}_{d:g}x{l:g}',family=entry['family'],platform_local_mm=[0,0,l/2],
            dimension_only=True,reference=user['source_file']+' / '+entry['sheet']+'!'+item['source_cell'],
            source_sha256=user['source_sha256'],platform_reference='NOMINAL_ENDOSSEOUS_BODY_TOP'))
    return result

# Libraries of one implant system that differ only in prosthetic platform.
# The proposal always reports narrow / standard / wide: a platform class the
# chosen library lacks is filled from its sibling libraries (9.24.8).
SYSTEMS=(
    ('BTI_P25','BTI_P30','BTI_P30X','BTI_INT_UNI','BTI_INT_UNIPLUS'),
    ('BTI_TINY','BTI_EXT_UNI','BTI_EXT_UNIPLUS'),
    ('ASTRA_EV_S','ASTRA_EV_C'),
)

def siblings(key):
    for system in SYSTEMS:
        if key in system:return tuple(k for k in system if k!=key)
    return ()

def hierarchy_rows(key):
    """Rows of ``key`` plus sibling-library rows for the platform classes it lacks.

    Sibling rows keep the chosen library's family (the search compares one
    system) and carry their own library in ``library`` / ``library_family``.
    """
    from .implant_platforms import platform_class
    own=rows(key)
    if not own:return own
    family=own[0]['family'];present={platform_class(r) for r in own};extra=[]
    for other in siblings(key):
        for row in rows(other):
            group=platform_class(row)
            if group in present:continue
            extra.append(dict(row,family=family,library=other,library_family=row['family']))
    return own+extra

def nominal_body_mesh(diameter,length,segments=64):
    """Circumscribed nominal body cylinder, without an invented thread or collar."""
    if not np.isfinite([diameter,length]).all() or min(diameter,length)<=0:raise ValueError('Medidas inválidas.')
    radius=diameter/(2*math.cos(math.pi/segments))
    angles=np.arange(segments)*2*math.pi/segments
    ring=np.c_[radius*np.cos(angles),radius*np.sin(angles)]
    vertices=np.vstack((np.c_[ring,np.full(segments,-length/2)],np.c_[ring,np.full(segments,length/2)],[[0,0,-length/2],[0,0,length/2]]))
    faces=[]
    for i in range(segments):
        j=(i+1)%segments
        faces.extend(((i,j,j+segments),(i,j+segments,i+segments),(2*segments,j,i),(2*segments+1,i+segments,j+segments)))
    return vertices,np.asarray(faces,dtype=np.int64)

def inside_envelope(vertices_local,diameter,length,tolerance=.05):
    """True when a local mesh (platform at +length/2, axis +Z) fits the nominal envelope."""
    v=np.asarray(vertices_local,float)
    radial=np.linalg.norm(v[:,:2],axis=1)
    return bool(radial.max()<=diameter/2+tolerance and v[:,2].min()>=-length/2-tolerance and v[:,2].max()<=length/2+tolerance)
