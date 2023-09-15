# NSD-Flat
[[`GitHub`]](https://github.com/clane9/NSD-Flat) [[🤗 `Hugging Face Hub`]](https://huggingface.co/datasets/clane9/NSD-Flat)

![Examples](.github/images/examples.png)

A Hugging Face dataset of pre-processed brain activity flat maps from the [Natural Scenes Dataset](https://naturalscenesdataset.org/), constrained to a visual cortex region of interest and rendered as PNG images.

## Load the dataset

Load the dataset from [Hugging Face Hub](https://huggingface.co/datasets/clane9/NSD-Flat)

```python
from datasets import load_dataset

dataset = load_dataset("clane9/NSD-Flat", split="train")
```

## Building the dataset

### 1. Download source data

Run [`download_data.sh`](download_data.sh) to download the required source data:

- NSD stimuli images and presentation info
- COCO annotations
- NSD beta activity maps in fsaverge surface space

```bash
bash download_data.sh
```

### 2. Convert the COCO annotations

Run  [`convert_nsd_annotations.py`](convert_nsd_annotations.py) to crop and reorganize the COCO annotations for NSD.

```bash
python convert_nsd_annotations.py
```

### 3. Generate the dataset

Run [`generate_dataset.py`](generate_dataset.py) to generate the huggingface dataset in Arrow format.

```bash
python generate_dataset.py --img_size 256 --workers 8
```

## Citation

If you find this dataset useful, please consider citing:

```
@article{allen2022massive,
  title     = {A massive 7T fMRI dataset to bridge cognitive neuroscience and artificial intelligence},
  author    = {Allen, Emily J and St-Yves, Ghislain and Wu, Yihan and Breedlove, Jesse L and Prince, Jacob S and Dowdle, Logan T and Nau, Matthias and Caron, Brad and Pestilli, Franco and Charest, Ian and others},
  journal   = {Nature neuroscience},
  volume    = {25},
  number    = {1},
  pages     = {116--126},
  year      = {2022},
  publisher = {Nature Publishing Group US New York}
}
```

```
@misc{lane2023nsdflat,
  author       = {Connor Lane},
  title        = {NSD-Flat: Pre-processed brain activity flat maps from the Natural Scenes Dataset},
  howpublished = {\url{https://huggingface.co/datasets/clane9/NSD-Flat}},
  year         = {2023},
}
```

## License

Usage of this dataset constitutes agreement to the [NSD Terms and Conditions](https://cvnlab.slite.page/p/IB6BSeW_7o/Terms-and-Conditions).