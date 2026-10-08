"""Run the production ratchet, pure-layer dependency rule and unit suite."""
import ast,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(root/'tools/metrics.py'),str(root)],check=True)
for path in (root/'pipeline_core').rglob('*.py'):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):modules=[a.name for a in node.names]
        elif isinstance(node,ast.ImportFrom):modules=[node.module or '']
        else:continue
        if any(name.split('.')[0] in {'bpy','bmesh','mathutils'} or name.startswith(('dsg.blender','dsg.engines')) for name in modules):raise SystemExit(f'PURE_LAYER_IMPORT_VIOLATION {path.name}')
subprocess.run([sys.executable,'-m','unittest','discover','-s',str(root/'tests_pure'),'-p','test_*.py','-v'],check=True)
subprocess.run([sys.executable,str(root/'tools/gen_index.py'),str(root),'--check'],check=True)
print('DSG_QUALITY_GATE_PASS',flush=True)
