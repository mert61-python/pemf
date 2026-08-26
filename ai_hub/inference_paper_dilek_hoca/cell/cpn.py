import torch
import celldetection as cd
import cv2
import numpy as np

__all__ = ['contours2labels', 'CpnInterface']


def contours2labels(contours, size, overlap=False, max_iter=999):
    labels = cd.data.contours2labels(cd.asnumpy(contours), size, initial_depth=3)

    if not overlap:
        kernel = cv2.getStructuringElement(1, (3, 3))
        mask_sm = np.sum(labels > 0, axis=-1)
        mask = mask_sm > 1  # all overlaps
        if mask.any():
            mask_ = mask_sm == 1  # all cores
            lbl = np.zeros(labels.shape[:2], dtype='float64')
            lbl[mask_] = labels.max(-1)[mask_]
            for _ in range(max_iter):
                lbl_ = np.copy(lbl)
                m = mask & (lbl <= 0)
                if not np.any(m):
                    break
                lbl[m] = cv2.dilate(lbl, kernel=kernel)[m]
                if np.allclose(lbl_, lbl):
                    break
        else:
            lbl = labels.max(-1)
        labels = lbl.astype('int')
    return labels


class CpnInterface:
    def __init__(self, model, device=None, **kwargs):
        self.device = ('cuda' if torch.cuda.is_available() else 'cpu') if device is None else device
        model = cd.resolve_model(model, **kwargs)
        if not isinstance(model, cd.models.LitCpn):
            model = cd.models.LitCpn(model)
        self.model = model.to(device)
        self.model.eval()
        self.model.requires_grad_(False)
        self.tile_size = 1664
        self.overlap = 384

    def __call__(
            self,
            img,
            div=255,
            reduce_labels=True,
            return_labels=True,
            return_viewable_contours=True,
    ):
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        img = img / div
        x = cd.data.to_tensor(img, transpose=True, dtype=torch.float32)[None]
        with torch.no_grad():
            out = cd.asnumpy(self.model(x, crop_size=self.tile_size,
                                        stride=max(64, self.tile_size - self.overlap)))
            # if torch.cuda.device_count():
            #     print(cd.GpuStats())

        contours, = out['contours']
        boxes, = out['boxes']
        scores, = out['scores']

        labels = None
        if return_labels or return_viewable_contours:
            labels = contours2labels(contours, img.shape[:2], overlap=not reduce_labels)

        return dict(
            contours=contours,
            labels=labels,
            boxes=boxes,
            scores=scores
        )
