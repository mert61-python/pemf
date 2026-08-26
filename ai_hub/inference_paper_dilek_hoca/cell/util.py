from imageio.v2 import imread as _imread
from shutil import copy2
import tifffile as tif

__all__ = ['imread', 'imsave', 'copy_skimage_data']


def imread(filename):
    if filename.split('.')[-1] in ('tiff', 'tif'):
        return tif.imread(filename)
    return _imread(filename)


def imsave(filename, img, compression="zlib"):
    tif.imwrite(filename, img, compression=compression)


def copy_skimage_data(dst='examples'):
    from skimage import data
    from os import makedirs
    from os.path import dirname, join, isfile
    from glob import glob

    makedirs(dst, exist_ok=True)

    for f in glob(join(dirname(data.__file__), '*.png')):
        copy2(f, dst)
