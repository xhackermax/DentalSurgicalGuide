"""Probe the external PyTorch runtime without importing it into Blender."""
import argparse
import json
import sys
from pathlib import Path

def probe(site):
    sys.path.insert(0, str(site))
    import torch
    cpu = torch.tensor([[1., 2.], [3., 4.]])
    expected = cpu @ cpu
    cuda = bool(torch.cuda.is_available())
    result = {'ready': True, 'cuda': cuda, 'device': 'CUDA' if cuda else 'CPU', 'torch': torch.__version__, 'gpu_name': '', 'vram_total_gb': 0., 'vram_free_gb': 0.}
    if cuda:
        # is_available alone does not detect unsupported GPU architectures.
        value = cpu.to('cuda') @ cpu.to('cuda')
        torch.cuda.synchronize()
        if not torch.allclose(value.cpu(), expected):
            raise RuntimeError('CUDA no supera la comprobación numérica')
        conv = torch.nn.Conv3d(1, 1, 3, bias=False, device='cuda')
        with torch.no_grad():
            conv.weight.fill_(1.)
            result3d = conv(torch.ones((1, 1, 8, 8, 8), device='cuda'))
        if not torch.allclose(result3d.cpu(), torch.full((1, 1, 6, 6, 6), 27.)):
            raise RuntimeError('CUDA/cuDNN no supera la convolución 3D')
        free, total = torch.cuda.mem_get_info()
        result.update(gpu_name=torch.cuda.get_device_name(), vram_total_gb=total / 2**30, vram_free_gb=free / 2**30, capability=list(torch.cuda.get_device_capability()))
    version_file = Path(torch.__file__).parent / 'version.py'
    result.update(version_file=str(version_file.resolve()), version_mtime_ns=version_file.stat().st_mtime_ns)
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('site')
    parser.add_argument('output')
    args = parser.parse_args()
    try:
        result = probe(args.site)
    except Exception as exc:
        result = {'ready': False, 'cuda': False, 'device': 'CPU', 'error': f'{type(exc).__name__}: {exc}'}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if not result['ready']:
        raise RuntimeError(result['error'])
    print('DSG_COMPUTE_PROBE_PASS', result['device'], result['torch'], flush=True)

if __name__ == '__main__':
    main()
