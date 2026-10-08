"""Generate/check the source index without importing DSG or Blender.

python dsg/tools/gen_index.py dsg --write
python dsg/tools/gen_index.py dsg --check
"""
import argparse
import ast
import hashlib
from pathlib import Path

BLENDER = {'bpy', 'bmesh', 'mathutils', 'gpu', 'blf', 'bpy_extras'}
EXCLUDED = {'tests', 'tests_pure', 'tests_blender', '__pycache__', 'offline_runtime'}
HOSTS = {'_dicom_parts': 'dicom_module', '_guide_parts': 'guide_module',
         '_alignment_parts': 'alignment_module'}


def cell(value):
    return str(value).replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')


def attribute(cls, name):
    for node in cls.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            if isinstance(value, ast.Constant):
                return str(value.value)
    return ''


def symbols(body, prefix=''):
    # Include methods and nested definitions, identified by qualified name.
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = prefix + node.name
            yield name, node
            yield from symbols(node.body, name + '.')
        else:
            fields = dict(ast.iter_fields(node))
            for field in ('body', 'orelse', 'finalbody'):
                yield from symbols(fields.get(field, []), prefix)
            for handler in fields.get('handlers', []):
                yield from symbols(handler.body, prefix)


def generate(root):
    files = sorted(p for p in root.rglob('*.py')
                   if not EXCLUDED.intersection(p.relative_to(root).parts))
    digest = hashlib.sha256()
    parsed = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        digest.update(rel.encode('utf-8') + b'\0' + data + b'\0')
        src = data.decode('utf-8-sig')
        parsed.append((rel, src, ast.parse(src, filename=rel)))
    version_tree = next(tree for rel, _, tree in parsed if rel == 'version.py')
    version = next(ast.literal_eval(n.value) for n in version_tree.body
                   if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'DSG_VERSION' for t in n.targets))
    out = [f'# DSG {".".join(map(str, version))} · Índice del código', '',
           '> Generado con AST; no ejecuta ni importa el addon. No editar a mano.', '',
           f'Archivos Python productivos: **{len(parsed)}**. SHA-256 del conjunto de fuentes: `{digest.hexdigest()}`.', '',
           'Incluye clases, funciones, métodos y definiciones anidadas. Los enlaces abren el archivo; '
           'la columna Línea indica la ubicación exacta. Los números cambian al editar el código.', '',
           'La dependencia Blender indica imports directos, incluso diferidos; su ausencia no demuestra '
           'que un módulo sea puro. Los fragmentos comparten el namespace de su anfitrión.', '',
           'Regenerar: `python dsg/tools/gen_index.py dsg --write`. '
           'Comprobar vigencia: `python dsg/tools/gen_index.py dsg --check`.', '']
    operators = []
    for rel, src, tree in parsed:
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add((node.module or '').split('.')[0])
        uses = ', '.join(sorted(imports & BLENDER)) or 'ninguno directo'
        host = HOSTS.get(rel.split('/')[0])
        meta = f'{len(src.splitlines())} líneas · imports Blender: {uses}'
        if host:
            meta += f' · namespace de `{host}`'
        out += [f'## [{rel}](../{rel})', '', meta, '',
                '| Línea | Símbolo | Descripción / bl_idname |', '|---:|---|---|']
        for name, node in symbols(tree.body):
            description = (ast.get_docstring(node) or '').strip().split('\n')[0][:180]
            kind = 'class ' if isinstance(node, ast.ClassDef) else ''
            if isinstance(node, ast.ClassDef):
                idname, label = attribute(node, 'bl_idname'), attribute(node, 'bl_label')
                if idname:
                    description = f'`{idname}` · {label}'
                    operators.append((idname, label, name, rel, node.lineno))
            out.append(f'| {node.lineno} | {kind}`{cell(name)}` | {cell(description)} |')
        out.append('')
    out += ['## Operadores, paneles y menús por bl_idname', '',
            '| bl_idname | Etiqueta | Clase | Archivo | Línea |', '|---|---|---|---|---:|']
    for idname, label, name, rel, line in sorted(operators):
        out.append(f'| `{cell(idname)}` | {cell(label)} | `{cell(name)}` | [{rel}](../{rel}) | {line} |')
    return '\n'.join(out) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = generate(args.root)
    target = args.root / 'docs/CODEMAP_INDEX.md'
    if args.check:
        if not target.is_file() or target.read_text(encoding='utf-8') != result:
            raise SystemExit('CODEMAP_INDEX_STALE: ejecutar gen_index.py --write')
        print('CODEMAP_INDEX_PASS')
    elif args.write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result, encoding='utf-8')
        print('CODEMAP_INDEX_WRITTEN')
    else:
        print(result, end='')


if __name__ == '__main__':
    main()
