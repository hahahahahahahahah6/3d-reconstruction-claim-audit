"""Offline AST and Markdown checks; source is never executed."""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import sys

from . import __version__
from .phrases import CLAIMS, DENIALS, GENERIC_NAMES

TSDF = {'ScalableTSDFVolume', 'UniformTSDFVolume'}
MESH = {'create_from_point_cloud_poisson', 'create_from_point_cloud_alpha_shape', 'create_from_point_cloud_ball_pivoting', 'create_from_rgbd_image'}
COLMAP = {'incremental_mapping', 'global_mapper', 'triangulate_points'}
DETECTORS = {'SIFT_create', 'ORB_create', 'AKAZE_create', 'BRISK_create'}
MATCHERS = {'BFMatcher', 'FlannBasedMatcher'}


def normalize(text):
    return re.sub(r'\s+', ' ', text.lower().replace("n't", ' not').replace('-', ' ')).strip()


def matches(text, phrases):
    found = []
    for phrase in sorted(phrases, key=lambda x: (-len(x), x)):
        pattern = r'\b' + re.escape(phrase) + r'\b'
        if re.search(pattern, text):
            found.append(phrase)
            text = re.sub(pattern, ' ', text)
    return found, text


def documentation(text):
    lines = []
    fence = None
    for line in text.splitlines():
        opening = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if re.match(r'^ {0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}\s*$', line):
                fence = None
            continue
        if opening:
            fence = opening.group(1)
            continue
        lines.append(line)
    claims, denials = [], []
    for paragraph in re.split(r'\n\s*\n', '\n'.join(lines)):
        negative, remaining = matches(normalize(paragraph), DENIALS)
        positive, _ = matches(remaining, CLAIMS)
        claims.extend(positive)
        denials.extend(negative)
    return claims, denials


def evidence(source):
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    nodes = list(ast.walk(tree))
    shadows = {n.name for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    aliases = {}
    gates = set()
    for n in nodes:
        if isinstance(n, ast.Import):
            for item in n.names:
                aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
                gates.add(item.name.split('.')[0])
        elif isinstance(n, ast.ImportFrom) and n.module:
            gates.add(n.module.split('.')[0])
            for item in n.names:
                aliases[item.asname or item.name] = n.module + '.' + item.name
    bindings = {}
    for n in nodes:
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for target in targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        bindings[name.id] = n.value
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            for item in n.items:
                if item.optional_vars:
                    for name in ast.walk(item.optional_vars):
                        if isinstance(name, ast.Name):
                            bindings[name.id] = item.context_expr
    def resolve(n, seen=None):
        seen = set() if seen is None else seen
        if isinstance(n, ast.Name):
            if n.id in shadows or n.id in seen:
                return ''
            if n.id in bindings:
                return resolve(bindings[n.id], seen | {n.id})
            return aliases.get(n.id, n.id)
        if isinstance(n, ast.Call):
            return resolve(n.func, seen)
        if isinstance(n, ast.Attribute):
            base = resolve(n.value, seen)
            return base + '.' + n.attr if base else ''
        return ''
    def name(n):
        resolved = resolve(n)
        return resolved.split('.')[-1] if resolved else ''
    def valid(n):
        terminal = n.attr if isinstance(n, ast.Attribute) else n.id if isinstance(n, ast.Name) else ''
        return terminal not in shadows and name(n) not in shadows and bool(resolve(n))
    def volume(n):
        return isinstance(n, ast.Call) and valid(n.func) and name(n.func) in TSDF
    calls = [n for n in nodes if isinstance(n, ast.Call)]
    parts = set()
    for call in calls:
        f = call.func
        if not valid(f):
            continue
        terminal = name(f)
        resolved = resolve(f)
        imported_name = isinstance(f, ast.Name) and f.id in aliases and '.' in resolved
        if terminal in GENERIC_NAMES and (isinstance(f, ast.Attribute) or imported_name):
            return True
        if 'open3d' in gates:
            if isinstance(f, ast.Attribute) and f.attr in MESH:
                return True
            if isinstance(f, ast.Attribute) and f.attr == 'integrate':
                base = f.value
                if volume(base) or (isinstance(base, ast.Name) and base.id not in shadows and volume(bindings.get(base.id))):
                    return True
        def library_call(library, names):
            direct = (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                      and resolve(f.value) == library and f.attr in names)
            imported = imported_name and resolved.startswith(library + '.') and terminal in names
            return direct or imported
        if 'pycolmap' in gates and library_call('pycolmap', COLMAP):
            return True
        if 'gsplat' in gates and library_call('gsplat', {'rasterization'}):
            return True
        if 'cv2' in gates:
            if resolved == 'cv2.sfm.reconstruct':
                return True
            if library_call('cv2', DETECTORS | MATCHERS | {'findEssentialMat', 'triangulatePoints'}):
                if terminal in DETECTORS:
                    parts.add('detector')
                if terminal in MATCHERS:
                    parts.add('matcher')
                if terminal in {'findEssentialMat', 'triangulatePoints'}:
                    parts.add(terminal)
    return len(parts) == 4


def audit(repo='.', ignore=()):
    root = Path(repo)
    if not root.is_dir() or not os.access(str(root), os.R_OK | os.X_OK):
        raise OSError('Repository must be a readable directory: ' + str(root))
    claims, denials, production, tests = [], [], [], []
    for directory, dirs, files in os.walk(str(root), onerror=lambda error: (_ for _ in ()).throw(error), followlinks=False):
        def skipped(path):
            relative = path.relative_to(root).as_posix()
            return path.is_symlink() or any(relative.startswith(prefix) for prefix in ignore)
        dirs[:] = sorted(d for d in dirs if not skipped(Path(directory) / d))
        for filename in sorted(files):
            path = Path(directory) / filename
            if skipped(path):
                continue
            relative = path.relative_to(root)
            components = relative.parts[:-1]
            if relative.as_posix() == 'README.md' or (path.suffix == '.md' and 'docs' in components):
                positive, negative = documentation(path.read_text(encoding='utf-8'))
                claims.extend(positive)
                denials.extend(negative)
            if path.suffix != '.py' or any(c in {'fixtures', 'docs', 'examples'} for c in components):
                continue
            if evidence(path.read_text(encoding='utf-8')):
                is_test = 'tests' in components or filename.startswith('test_') or filename.endswith('_test.py')
                (tests if is_test else production).append(relative.as_posix())
    findings = []
    if claims and not production:
        severity = 'MEDIUM' if tests else 'HIGH'
        findings.append({'id': 'documented-3d-reconstruction-claim-false', 'severity': severity,
                         'message': 'Evidence exists only in tests.' if tests else 'No production evidence supports the documented claim.'})
    if denials and production:
        findings.append({'id': 'documented-no-3d-reconstruction-claim-false', 'severity': 'HIGH',
                         'message': 'Production evidence contradicts the documented denial.'})
    return {'verdict': 'FAIL' if findings else 'PASS', 'findings': findings,
            'claims': claims, 'denials': denials, 'production_evidence': production, 'test_evidence': tests}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, self.prog + ': error: ' + message + '\n')


def main(argv=None):
    parser = Parser(prog='3d-reconstruction-claim-audit')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    command = sub.add_parser('audit')
    command.add_argument('repo', nargs='?', default='.')
    command.add_argument('--json', action='store_true')
    command.add_argument('--verbose', action='store_true')
    command.add_argument('--ignore', action='append', default=[], metavar='PREFIX')
    command.add_argument('--fail-on', choices=('high', 'medium'), default='high')
    args = parser.parse_args(argv)
    try:
        result = audit(args.repo, args.ignore)
    except (OSError, UnicodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(result['verdict'])
        for finding in result['findings']:
            print('{severity} {id}: {message}'.format(**finding))
        if args.verbose:
            print('Production evidence: ' + ', '.join(result['production_evidence']))
            print('Test evidence: ' + ', '.join(result['test_evidence']))
    return 2 if any(f['severity'] == 'HIGH' or args.fail_on == 'medium' for f in result['findings']) else 0
