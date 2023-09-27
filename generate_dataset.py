import argparse
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Union

import datasets as dsets
import h5py
import nibabel as nib
import numpy as np
import pandas as pd
from PIL import Image
from sklearn.preprocessing import scale

from resample import Bbox, Resampler
from surface import load_fsaverage_flat

logging.basicConfig(
    format="[%(levelname)s %(asctime)s]: %(message)s",
    level=logging.INFO,
    datefmt="%y-%m-%d %H:%M:%S",
)

StrOrPath = Union[str, Path]

ROOT = Path(__file__).parent

SEED = 2023
NUM_SUBS = 8
SUBS = [f"subj{ii:02d}" for ii in range(1, NUM_SUBS + 1)]
NUM_TRIALS = 30000
IMG_SIZE = 425

# Available sessions per subject.
# Last three sessions are test set.
MAX_SESSIONS = 40
NUM_SESSIONS = {
    "subj01": 40,
    "subj02": 40,
    "subj03": 32,
    "subj04": 30,
    "subj05": 40,
    "subj06": 32,
    "subj07": 40,
    "subj08": 30,
}
TRIALS_PER_SESSION = NUM_TRIALS // MAX_SESSIONS

# Pixel resolution in mm for rasterized activity maps
PIXEL_SIZE = 1.0
# Map bounding box in mm (left, right, bottom, top)
MAP_RECT = (-100, 100, -120, 95)
# Num sigma value max for quantizing acivity data to uint8
VMAX = 2.5


def generate_dataset(split: str = "train", img_size: Optional[int] = None, debug: bool = False):
    logging.info("Loading NSD image stimuli")
    images = h5py.File(ROOT / "data/NSD/nsddata_stimuli/stimuli/nsd/nsd_stimuli.hdf5")
    images = images["imgBrick"]
    logging.info("Images shape: %s", images.shape)

    logging.info("Loading NSD stimulus info")
    long_stim_info_path = ROOT / "data/nsd_stim_info_long.csv"
    long_stim_info = pd.read_csv(long_stim_info_path, index_col=[0, 1])

    logging.info("Loading annotations")
    annotations = pd.read_json(ROOT / "data/nsd_annotations.jsonl", lines=True)
    annotations = annotations.set_index("nsd_id")

    for subid, sub in enumerate(SUBS):
        logging.info("Generating data for subject %s", sub)

        mask_paths = {
            hemi: ROOT / f"resources/{sub}.{hemi}.all-vertices_fsaverage_space.npy"
            for hemi in ["lh", "rh"]
        }
        masks = {hemi: np.load(path) > 0 for hemi, path in mask_paths.items()}
        combined_mask = np.concatenate([masks[hemi] for hemi in ["lh", "rh"]])
        logging.info("%s: size of ROI: %d", sub, combined_mask.sum())

        resampler = get_resampler(combined_mask, pixel_size=PIXEL_SIZE, rect=MAP_RECT)
        logging.info("%s: size of raster mask: %d", sub, resampler.mask_.sum())

        if split == "train":
            sessions = range(NUM_SESSIONS[sub] - 3)
        elif split == "test":
            sessions = range(NUM_SESSIONS[sub] - 3, NUM_SESSIONS[sub])
        else:
            raise ValueError(f"Unrecognized split {split}")
        logging.info("%s: %s sessions:\n\t%s", sub, split, list(sessions))

        for sesid in sessions:
            activity = load_session_activity(sub, sesid, masks)

            for ii, act in enumerate(activity):
                trialid = sesid * TRIALS_PER_SESSION + ii
                trial_info = long_stim_info.loc[(subid, trialid)].to_dict()
                nsdid = trial_info["nsdId"]

                # Stimulus image, resized
                img = images[nsdid]
                img = Image.fromarray(img, mode="RGB")
                if img_size:
                    img = img.resize(
                        (img_size, img_size), resample=Image.Resampling.BICUBIC
                    )

                # Map and rasterize activity
                act = resampler.transform(act)
                act = resampler.apply_mask(act, fill_value=0.0)
                act = quantize(act, vmin=-VMAX, vmax=VMAX)
                # Activity maps use lower origin by default. Set to upper for better
                # huggingface dataset preview.
                act = np.flipud(act)
                act = Image.fromarray(act, mode="L")

                anns = annotations.loc[nsdid].to_dict()

                record = {
                    "subject_id": subid,
                    "trial_id": trialid,
                    "session_id": sesid,
                    "nsd_id": nsdid,
                    "image": img,
                    "activity": act,
                    "subject": sub,
                    **{k: trial_info[k] for k in ["flagged", "BOLD5000", "shared1000"]},
                    **{
                        k: anns[k]
                        for k in ["coco_split", "coco_id", "objects", "captions"]
                    },
                    "repetitions" : {
                        k: v for k, v in trial_info.items() if "_rep" in k
                    }
                }
                yield record
            
            if debug:
                return


def get_resampler(
    mask: np.ndarray, pixel_size: float, rect: Optional[Bbox] = None
) -> Resampler:
    """
    Create a `Resampler` for creating rasterized brain activity maps.
    """
    surf = load_fsaverage_flat()
    patch = surf.extract_patch(mask=mask)
    resampler = Resampler(pixel_size=pixel_size, rect=rect)
    resampler.fit(patch.points)
    return resampler



def load_session_activity(
    sub: str, sesid: int, masks: Dict[str, np.ndarray]
) -> np.ndarray:
    """
    Load NSD surface-mapped brain activity for one subject and session.
    """
    hemi_activities = []
    for hemi in ["lh", "rh"]:
        img_path = (
            ROOT
            / "data"
            / "NSD"
            / "nsddata_betas"
            / "ppdata"
            / sub
            / "fsaverage"
            / "betas_fithrf_GLMdenoise_RR"
            / f"{hemi}.betas_session{sesid + 1:02d}.mgh"
        )

        img = nib.load(img_path)
        activity = np.ascontiguousarray(np.squeeze(img.get_fdata()).T)

        # Project onto ROI
        activity = activity[:, masks[hemi]]

        # zscore within session and convert to float32, following Algonauts
        activity = scale(activity)
        activity = activity.astype(np.float32)
        hemi_activities.append(activity)

    activity = np.concatenate(hemi_activities, axis=1)
    return activity


def quantize(data: np.ndarray, vmin: float = -2.5, vmax: float = 2.5) -> np.ndarray:
    """
    Quantize continuous data with standard normal data to uint8.
    """
    data = np.clip(data, vmin, vmax)
    data = (data - vmin) / (vmax - vmin)
    data = (255 * data).astype(dtype="uint8")
    return data


def get_transforms(img_size: int):
    def transforms(examples):
        examples["image"] = [
            image.resize((img_size, img_size), resample=Image.Resampling.BICUBIC)
            for image in examples["image"]
        ]
        return examples

    return transforms


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split",
        metavar="SPLIT",
        type=str,
        default="train",
        choices=["train", "test"],
        help="dataset split to generate",
    )
    parser.add_argument(
        "--img_size",
        "--sz",
        metavar="H",
        type=int,
        default=None,
        help="optional image size to resize to",
    )
    parser.add_argument(
        "--workers",
        "-j",
        metavar="N",
        type=int,
        default=4,
        help="number of data workers",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="debug mode",
    )
    args = parser.parse_args()

    dset = dsets.Dataset.from_generator(
        generate_dataset,
        gen_kwargs={"split": args.split, "img_size": args.img_size, "debug": args.debug},
    )

    logging.info("Converting images and activity to Image features")
    dset = dset.cast_column("image", dsets.Image())
    dset = dset.cast_column("activity", dsets.Image())

    logging.info("Saving dataset")
    img_size = args.img_size if args.img_size else IMG_SIZE
    suffix = "-debug" if args.debug else ""
    out_dir = ROOT / f"processed/size-{img_size}{suffix}/{args.split}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    dset.save_to_disk(out_dir, num_proc=args.workers)
