"""AST ratchet for production Python; tests are reported separately."""
import ast,json,sys
from pathlib import Path

EXCLUDE={'tests','tests_pure','tests_blender','__pycache__'}
def silent(body):
    if len(body)!=1:return False
    node=body[0]
    if isinstance(node,(ast.Pass,ast.Continue)):return True
    if isinstance(node,ast.Return):
        value=node.value
        return value is None or isinstance(value,ast.Constant) and value.value in (None,False,'') or isinstance(value,(ast.List,ast.Set,ast.Tuple)) and not value.elts or isinstance(value,ast.Dict) and not value.keys
    return False
def scan(root):
    metrics=dict(broad_except=0,silent_except=0,global_stmt=0,getattr_hasattr=0,exec_calls=0,bpy_outside_blender=0,max_file_lines=0)
    for path in Path(root).rglob('*.py'):
        if any(part in EXCLUDE for part in path.relative_to(root).parts):continue
        src=path.read_text(encoding='utf-8-sig');metrics['max_file_lines']=max(metrics['max_file_lines'],len(src.splitlines()))
        for node in ast.walk(ast.parse(src,str(path))):
            if isinstance(node,ast.ExceptHandler) and (node.type is None or isinstance(node.type,ast.Name) and node.type.id in ('Exception','BaseException')):
                metrics['broad_except']+=1;metrics['silent_except']+=int(silent(node.body))
            elif isinstance(node,ast.Global):metrics['global_stmt']+=1
            elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                if node.func.id in ('getattr','hasattr'):metrics['getattr_hasattr']+=1
                elif node.func.id=='exec':metrics['exec_calls']+=1
            elif isinstance(node,(ast.Import,ast.ImportFrom)) and 'blender' not in path.relative_to(root).parts:
                modules=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or '']
                metrics['bpy_outside_blender']+=int(any(m.split('.')[0] in {'bpy','bmesh','mathutils'} for m in modules))
    return metrics
def compare(current,baseline):return {k:[baseline[k],v] for k,v in current.items() if v>baseline[k]}
if __name__=='__main__':
    root=Path(sys.argv[1]);baseline=Path(sys.argv[2]) if len(sys.argv)>2 else root/'tools/metrics_baseline.json'
    current=scan(root);print(json.dumps(current,indent=2))
    if '--update' in sys.argv:baseline.write_text(json.dumps(current,indent=2),encoding='utf-8')
    elif not baseline.is_file():raise SystemExit('Falta línea base; crea una explícitamente con --update')
    else:
        worse=compare(current,json.loads(baseline.read_text(encoding='utf-8')))
        if worse:raise SystemExit('METRICS_REGRESSION '+json.dumps(worse))
