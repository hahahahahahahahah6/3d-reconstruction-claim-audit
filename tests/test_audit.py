import ast
import contextlib
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

A = importlib.import_module("3d_reconstruction_claim_audit.audit")
P = importlib.import_module("3d_reconstruction_claim_audit.phrases")
EXPECTED_CLAIMS = ('3d reconstruction', 'neural radiance field', 'nerf', 'gaussian splatting', '3d gaussian splatting', 'photogrammetry', 'structure from motion', 'multi view stereo', 'three dimensional reconstruction', '3d scene reconstruction', 'reconstruct 3d', 'reconstructs 3d', 'reconstructing 3d', 'build 3d models from photos', 'builds 3d models from photos', 'build a 3d model from photos', 'turn photos into 3d models', 'turns photos into 3d models', 'turn images into 3d models', 'turns images into 3d models', 'photos to 3d', 'images to 3d', 'photo to 3d model', 'image to 3d model', 'multi view reconstruction', 'sparse reconstruction', 'dense reconstruction', 'point cloud from photos', 'point clouds from photos', 'point cloud from images', 'generate a point cloud', 'generates a point cloud', 'generate point clouds', 'mesh from photos', 'mesh from images', 'create a 3d mesh', 'creates a 3d mesh', '3d mesh from photos', 'novel view synthesis', '3d model from photos', '3d models from photos', '3d model from images', '3d scan from photos', 'scan to 3d model', 'reconstruct the scene in 3d', 'reconstructs the scene in 3d', 'depth to point cloud', 'rgbd reconstruction', '3d reconstruction from photos', '3d reconstruction from images')
EXPECTED_DENIALS = ('no 3d reconstruction', 'does not do 3d reconstruction', 'does not perform 3d reconstruction', 'does not support 3d reconstruction', 'without 3d reconstruction', 'no photogrammetry', 'does not do photogrammetry', 'does not support photogrammetry', 'no structure from motion', 'does not reconstruct 3d', 'does not build 3d models', 'no point cloud generation', 'does not generate point clouds', 'no mesh generation', 'does not generate meshes', 'no nerf', 'does not do nerf', 'no gaussian splatting', 'does not do gaussian splatting', 'no novel view synthesis', 'does not reconstruct scenes in 3d', '3d reconstruction not supported', 'no 3d model generation', 'does not create 3d models')
EXPECTED_GENERIC = ('reconstruct_3d', 'reconstruct3d', 'reconstruct_scene', 'reconstruct_from_images', 'reconstruct_mesh', 'reconstruct_point_cloud', 'build_3d_model', 'build_point_cloud', 'build_mesh', 'create_3d_model', 'create_point_cloud', 'generate_3d_model', 'generate_point_cloud', 'generate_mesh', 'photogrammetry', 'structure_from_motion', 'sfm_reconstruction', 'multi_view_stereo', 'mvs_reconstruction', 'gaussian_splatting', 'train_nerf', 'nerf_train', 'point_cloud_reconstruction', 'mesh_reconstruction')

GOOD = [
    'import open3d as o\nv=o.pipelines.integration.ScalableTSDFVolume()\nv.integrate(x)',
    'import open3d\nv=open3d.UniformTSDFVolume()\nv.integrate(x)',
    'import open3d\nopen3d.ScalableTSDFVolume().integrate(x)',
    *['import open3d as o\no.geometry.TriangleMesh.' + name + '(x)' for name in sorted(A.MESH)],
    *['import pycolmap\npycolmap.' + name + '(x)' for name in sorted(A.COLMAP)],
    'from pycolmap import incremental_mapping as mapping\nmapping(x)',
    'import pycolmap as p\np.incremental_mapping(x)',
    'import gsplat\ngsplat.rasterization(x)',
    'from gsplat import rasterization as r\nr(x)',
    'import gsplat as g\ng.rasterization(x)',
    'import cv2\ncv2.sfm.reconstruct(x)',
    'import cv2 as c\nc.sfm.reconstruct(x)',
    'import cv2\ncv2.SIFT_create()\ncv2.BFMatcher()\ncv2.findEssentialMat(x)\ncv2.triangulatePoints(x)',
    'from cv2 import ORB_create as d, FlannBasedMatcher as m, findEssentialMat as e, triangulatePoints as t\nd()\nm()\ne(x)\nt(x)',
    *['service.' + name + '(x)' for name in EXPECTED_GENERIC],
    'from worker import reconstruct_3d as run\nrun(x)',
    'from open3d.pipelines.integration import ScalableTSDFVolume as V\nv=V()\nv.integrate(x)',
    'import open3d\nv: object = open3d.ScalableTSDFVolume()\nv.integrate(x)',
    'import open3d\nwith open3d.ScalableTSDFVolume() as v:\n v.integrate(x)',
    'import open3d\nasync def f():\n async with open3d.ScalableTSDFVolume() as v:\n  v.integrate(x)',
]
BAD = [
    'import open3d', 'import pycolmap', 'import gsplat', 'import cv2',
    'import open3d\nv=open3d.ScalableTSDFVolume()',
    'import open3d\nv=open3d.ScalableTSDFVolume()\nv.extract_triangle_mesh()',
    'import open3d\nv=open3d.ScalableTSDFVolume()\nv.extract_point_cloud()',
    'import open3d\nv.integrate(x)',
    'import open3d\nv=Other()\nv.integrate(x)',
    'import open3d\no.geometry.RGBDImage.create_from_color_and_depth(x)',
    'import open3d\no.pipelines.registration.registration_icp(x)',
    *['import cv2\ncv2.' + name + '(x)' for name in ('solvePnP', 'findHomography', 'triangulatePoints', 'findEssentialMat')],
    'estimate_depth(x)', 'stitcher.stitch(x)', 'model.estimate_pose(x)',
    'cv2.calcOpticalFlowFarneback(x)', 'model.generate_image(x)',
    'import open3d\nopen3d.io.read_point_cloud(x)',
    'import open3d\nopen3d.io.read_triangle_mesh(x)', 'import trimesh\ntrimesh.load(x)',
    'open3d.visualization.draw_geometries(x)',
    'import subprocess\nsubprocess.run(["colmap", "mapper"])',
    '"service.reconstruct_3d(x)"\n# service.reconstruct_3d(x)',
    'service.reconstruct_3d', 'reconstruct_3d(x)', 'invalid syntax !',
    'import pycolmap\npycolmap.Reconstruction()',
    'from worker import reconstruct_3d\ndef reconstruct_3d(x): pass\nreconstruct_3d(x)',
    'def reconstruct_3d(x): pass\nservice.reconstruct_3d(x)',
    'import pycolmap\ndef incremental_mapping(x): pass\npycolmap.incremental_mapping(x)',
    'import gsplat\nclass C:\n def rasterization(self): pass\ngsplat.rasterization(x)',
    'import open3d\nclass ScalableTSDFVolume: pass\nv=open3d.ScalableTSDFVolume()\nv.integrate(x)',
    'import pycolmap\nwith Other() as pycolmap:\n pycolmap.incremental_mapping(x)',
    'import gsplat\ngsplat = Other()\ngsplat.rasterization(x)',
    'import open3d\nv=open3d.ScalableTSDFVolume()\nwith Other() as v:\n v.integrate(x)',
]
PIPE = ['cv2.SIFT_create()', 'cv2.BFMatcher()', 'cv2.findEssentialMat(x)', 'cv2.triangulatePoints(x)']
BAD += [
    'import pycolmap\npycolmap.other.incremental_mapping(x)',
    'import gsplat\ngsplat.other.rasterization(x)',
    'import pycolmap\npycolmap().incremental_mapping(x)',
    'import cv2\n' + '\n'.join('cv2.other.' + part.split('.', 1)[1] for part in PIPE),
]
BAD += ['import cv2\n' + '\n'.join(PIPE[:i] + PIPE[i+1:]) for i in range(4)]


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            code = A.main(['audit', str(self.root)] + list(args))
        return code, output.getvalue()

    def test_phrase_oracle(self):
        tree = ast.parse(Path(P.__file__).read_text())
        values = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)}
        self.assertEqual(values['CLAIMS'], EXPECTED_CLAIMS)
        self.assertEqual(values['DENIALS'], EXPECTED_DENIALS)
        self.assertEqual(values['GENERIC_NAMES'], EXPECTED_GENERIC)
        self.assertEqual((len(P.CLAIMS), len(P.DENIALS), len(set(P.GENERIC_NAMES))), (50, 24, 24))

    def test_bad_exact(self):
        self.write('README.md', '3d reconstruction')
        code, output = self.cli('--json')
        result = json.loads(output)
        self.assertEqual(code, 2)
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertEqual(result['findings'][0]['id'], 'documented-3d-reconstruction-claim-false')
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.assertIsInstance(result['findings'][0]['message'], str)

    def test_test_only(self):
        self.write('README.md', '3d reconstruction')
        self.write('tests/worker.py', GOOD[0])
        self.assertEqual(self.cli()[0], 0)
        self.assertIn('MEDIUM', self.cli()[1])
        self.assertEqual(self.cli('--fail-on', 'medium')[0], 2)

    def test_denial_exact(self):
        self.write('README.md', 'does not do 3d reconstruction')
        self.write('main.py', GOOD[0])
        result = A.audit(self.root)
        self.assertEqual(result['claims'], [])
        self.assertEqual(result['findings'][0]['id'], 'documented-no-3d-reconstruction-claim-false')
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.assertEqual(self.cli()[0], 2)

    def test_no_claim(self):
        self.write('main.py', GOOD[0])
        self.assertEqual(A.audit(self.root)['verdict'], 'PASS')

    def test_no_source_asymmetry(self):
        self.write('README.md', '3d reconstruction')
        self.assertEqual(self.cli()[0], 2)
        self.write('README.md', 'no 3d reconstruction')
        self.assertEqual(A.audit(self.root)['verdict'], 'PASS')

    def test_fences_inline_and_paragraphs(self):
        for marker in ('```', '~~~'):
            self.assertEqual(A.documentation('   '+marker+'text\n3d reconstruction\n   '+marker), ([], []))
        self.assertEqual(A.documentation('`3d-reconstruction`')[0], ['3d reconstruction'])
        self.assertEqual(A.documentation('3d\n\nreconstruction'), ([], []))
        self.assertEqual(A.documentation("doesn't do 3d reconstruction"), ([], ['does not do 3d reconstruction']))
        self.assertEqual(A.documentation('3d reconstruction from photos')[0], ['3d reconstruction from photos'])
        self.assertEqual(A.documentation('xnerfx'), ([], []))

    def test_all_phrase_matches(self):
        for phrase in EXPECTED_CLAIMS:
            with self.subTest(phrase=phrase):
                self.assertEqual(A.documentation(phrase)[0], [phrase])
        for phrase in EXPECTED_DENIALS:
            with self.subTest(phrase=phrase):
                self.assertEqual(A.documentation(phrase), ([], [phrase]))

    def test_split_modules(self):
        self.write('README.md', '3d reconstruction')
        self.write('a.py', 'import open3d\nv=open3d.ScalableTSDFVolume()')
        self.write('b.py', 'import open3d\nv.integrate(x)')
        self.assertEqual(self.cli()[0], 2)
        self.write('a.py', 'import cv2\n'+'\n'.join(PIPE[:2]))
        self.write('b.py', 'import cv2\n'+'\n'.join(PIPE[2:]))
        self.assertEqual(self.cli()[0], 2)

    def test_paths(self):
        self.write('README.md', '3d reconstruction')
        for name in ('fixtures/a.py', 'docs/a.py', 'examples/a.py'):
            self.write(name, GOOD[0])
        self.assertEqual(self.cli()[0], 2)
        for name in ('tests/a.py', 'test_a.py', 'a_test.py'):
            path = self.write(name, GOOD[0])
            self.assertEqual(self.cli('--fail-on', 'medium')[0], 2)
            self.assertEqual(A.audit(self.root)['findings'][0]['severity'], 'MEDIUM')
            path.unlink()
        external = self.write('fixtures/external.py', GOOD[0])
        (self.root/'link.py').symlink_to(external)
        (self.root/'linked').symlink_to(self.root/'fixtures', target_is_directory=True)
        self.assertEqual(self.cli()[0], 2)
        self.assertEqual(A.audit(self.root)['production_evidence'], [])

    def test_docs_and_ignore(self):
        self.write('notes.md', '3d reconstruction')
        self.assertEqual(A.audit(self.root)['verdict'], 'PASS')
        self.write('nested/docs/feature.md', '3d reconstruction')
        self.assertEqual(self.cli()[0], 2)
        self.assertEqual(self.cli('--ignore', 'nested', '--ignore', 'unused')[0], 0)
        self.write('app/main.py', GOOD[0])
        self.assertEqual(self.cli()[0], 0)
        self.assertEqual(self.cli('--ignore', 'app')[0], 2)

    def test_errors(self):
        with self.assertRaises(OSError):
            A.audit(self.root/'missing')
        for args in ([], ['audit', '--fail-on', 'HIGH'], ['audit', '--ignore'], ['wrong']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                A.main(args)
            self.assertEqual(caught.exception.code, 1)
        self.assertEqual(A.main(['audit', str(self.root/'missing')]), 1)

    def test_module_entry(self):
        result = subprocess.run([sys.executable, '-m', '3d_reconstruction_claim_audit', '--version'], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, '0.1.0'))


def good_test(source):
    def test(self):
        self.write('README.md', '3d reconstruction')
        self.write('app.py', source)
        self.assertTrue(A.evidence(source))
        self.assertEqual(self.cli()[0], 0)
        self.assertEqual(A.audit(self.root)['verdict'], 'PASS')
    return test


def bad_test(source):
    def test(self):
        self.write('README.md', '3d reconstruction')
        self.write('app.py', source)
        self.assertFalse(A.evidence(source))
        self.assertEqual(self.cli()[0], 2)
    return test


for index, source in enumerate(GOOD):
    setattr(AuditTests, 'test_good_route_%02d' % index, good_test(source))
for index, source in enumerate(BAD):
    setattr(AuditTests, 'test_not_evidence_%02d' % index, bad_test(source))

if __name__ == '__main__':
    unittest.main()
