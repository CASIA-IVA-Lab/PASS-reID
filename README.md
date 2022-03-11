![Python >=3.7](https://img.shields.io/badge/Python->=3.7-yellow.svg)
![PyTorch >=1.8](https://img.shields.io/badge/PyTorch->=1.8-blue.svg)

# Part-Aware Self-Supervised Pre-Training for Person Re-Identification [[pdf]](https://arxiv.org/pdf/2203.03931.pdf)
The *official* repository for [Part-Aware Self-Supervised Pre-Training for Person Re-Identification](https://arxiv.org/pdf/2203.03931.pdf).

## Requirements

### Installation
```bash
pip install -r requirements.txt
```
We recommend to use /torch=1.8.0 /torchvision=0.9.0 /timm=0.3.4 /cuda>11.1 /faiss-gpu=1.7.2/ A100 for training and evaluation. If you find some packages are missing, please install them manually.
You can refer to [DINO](https://github.com/facebookresearch/dino), [TransReID](https://github.com/damo-cv/TransReID) and [cluster-contrast-reid](https://github.com/alibaba/cluster-contrast-reid) to install the environment of pre-training, supervised ReID and unsupervised ReID, respectively. 

You can also refer to [TransReID-SSL](https://github.com/damo-cv/TransReID-SSL) to install the whole environments.

### Prepare Datasets

```bash
mkdir data
```

Download the datasets:
- [Market-1501](https://drive.google.com/file/d/0B8-rUzbwVRk0c054eEozWG9COHM/view)
- [MSMT17](https://arxiv.org/abs/1711.08565)
- [LUPerson](https://github.com/DengpanFu/LUPerson). We don't have the copyright of the LUPerson dataset. Please contact authors of LUPerson to get this dataset.

Then unzip them and rename them under the directory like

```
data
├── market1501
│   └── bounding_box_train
│   └── bounding_box_test
│   └── ..
├── MSMT17
│   └── train
│   └── test
│   └── ..
└── LUP
    └── images 
```

## Pre-trained Models
| Model         | Download |
| :------:      | :------: |
| ViT-S/16      | [link](https://drive.google.com/file/d/1q7oxT0vWvt0Ia0NMmdVlA3oUs0UCQq3C/view?usp=sharing) |
| ViT-B/16  | [link](https://drive.google.com/file/d/1sZUrabY6Lke-BJoxOEviX5ALJ017x4Ft/view?usp=sharing) |


Please download pre-trained models and put them into your custom file path.

## ReID performance

We have reproduced the performance to verify the reproducibility. The reproduced results may have a gap of about 0.1~0.2% with the numbers in the paper.

### Supervised ReID

##### Market-1501
| Model         | Image Size|mAP | Rrank-1 | Download |
| :------:      | :------: |:------: | :------: |:------: |
| ViT-S/16  | 256*128 | 92.2 | 96.3 |[model](https://drive.google.com/file/d/1e7QVo-0lJ9EUcRgJNIQ2gci2Pj1_ZE9M/view?usp=sharing) / [log](https://drive.google.com/file/d/1TsNEWoZ-Ry7otb9bLoz7mRLNFvUL5S6V/view?usp=sharing)|
| ViT-S/16  | 384*128 | 92.6 | 96.8 |[model](https://drive.google.com/file/d/1201j4ix92953te-o3FrrXh5sqxtTO7TE/view?usp=sharing) / [log](https://drive.google.com/file/d/1-CelgQud4Rux49mJBXT5_JlDrrrmgUqA/view?usp=sharing)|
| ViT-B/16  | 256*128 | 93.0 | 96.8 |[model](https://drive.google.com/file/d/104I1LStAfu52hlCMlx3eCIENIA_KMJUR/view?usp=sharing) / [log](https://drive.google.com/file/d/1m8UttTEbDKu3rrT37mZZGxlwZy8XYCVE/view?usp=sharing)|
| ViT-B/16  | 384*128 | 93.3 | 96.9 |[model](https://drive.google.com/file/d/1dYQjK4ycpXRfOJFoucbizQlKdytoKmpl/view?usp=sharing) / [log](https://drive.google.com/file/d/14iSJKf7a4AkMkMNJMChezZVRgYJ7YeyA/view?usp=sharing)|
##### MSMT17
| Model         | Image Size|mAP | Rrank-1 | Download |
| :------:      | :------: |:------: | :------: |:------: |
| ViT-S/16  | 256*128 | 69.1 | 86.5 |[model](https://drive.google.com/file/d/1or1Lj7Xvd_gmQIMEX_TvzcZsqOgNWoDk/view?usp=sharing) / [log](https://drive.google.com/file/d/1z-62DEt4PseMICFZm2fDwSniOgOrmI8Q/view?usp=sharing)|
| ViT-S/16  | 384*128 | 71.7 | 87.9 |[model](https://drive.google.com/file/d/1EV4r3W_oCFn0JrhgwWX1j3X1jJR-BlcN/view?usp=sharing) / [log](https://drive.google.com/file/d/1Li0kLN3yYT1knC3Yrt5oscBnxJozilf9/view?usp=sharing)|
| ViT-B/16  | 256*128 | 71.8 | 88.2 |[model](https://drive.google.com/file/d/1W18HEwF5P7qN8MqyacFXOHW0W5gwVUs4/view?usp=sharing) / [log](https://drive.google.com/file/d/1bGBYpaeMD9SZsBWApRmHaOrIgZOLSUF3/view?usp=sharing)|
| ViT-B/16  | 384*128 | 74.3 | 89.7 |[model](https://drive.google.com/file/d/1T-EVjOtw1fJ4Mk7k-fU7ZeAGjUtSrNbh/view?usp=sharing) / [log](https://drive.google.com/file/d/1Vp-qRDhsPU_q7JAFR0rGtu2s_rG05Yug/view?usp=sharing)|


### UDA ReID

##### MSMT2Market
| Model         | Image Size| mAP | Rank-1 | Download |
| :------:      | :------: |:------: | :------: |:------: |
| ViT-S/16      | 256*128 | 90.2 | 95.8 |[model](https://drive.google.com/file/d/1m1x-HFxOCXYT8S4kZVU-sTroFapStjuC/view?usp=sharing) / [log](https://drive.google.com/file/d/1NyPN_IaRBXuc4QjkUFlTkD2osacdxwyI/view?usp=sharing)|

##### Market2MSMT
| Model         | Image Size| mAP | Rank-1 | Download |
| :------:      | :------: |:------: | :------: |:------: |
| ViT-S/16      | 256*128 | 49.1 | 72.7  |[model](https://drive.google.com/file/d/1dxKXUwN-qgHXDbdRtqwbGWx8mMpXFuJc/view?usp=sharing) / [log](https://drive.google.com/file/d/16iA42YyhYskcYoN1Gho7Eojuort2wGRw/view?usp=sharing)|

### USL ReID

##### Market-1501
| Model         | Image Size| mAP | Rank-1 | Download |
| :------:      | :------: |:------: | :------: |:------: |
| ViT-S/16      | 256*128 | 88.7 | 95.0 |[model](https://drive.google.com/file/d/1r8MYGeqS50e6C5Zjk-tazlpSJpz85mMt/view?usp=sharing) / [log](https://drive.google.com/file/d/1YFvY3h0plvA-GT1gXdzJViXplQjQp-zp/view?usp=sharing)|


##### MSMT17
| Model         | Image Size| mAP | Rank-1 | Download |
| :------:      | :------: |:------: | :------: |:------: |
| ViT-S/16      | 256*128 | 41.0 | 67.0 |[model](https://drive.google.com/file/d/1ooQ0spMoHlW6wMAPM14T9lQvzu-CinhG/view?usp=sharing) / [log](https://drive.google.com/file/d/1G2hZ9gUEOhpQfZ3zxPeWEgD11fdT9sgx/view?usp=sharing)|


## Acknowledgment
Our implementation is mainly based on the following codebases. We gratefully thank the authors for their wonderful works.

[TransReID-SSL](https://github.com/damo-cv/TransReID-SSL),
[LUPerson](https://github.com/DengpanFu/LUPerson), [DINO](https://github.com/facebookresearch/dino), [TransReID](https://github.com/damo-cv/TransReID), [cluster-contrast-reid](https://github.com/alibaba/cluster-contrast-reid).

## Citation

If you find this code useful for your research, please cite our paper

```
@article{zhu2022part,
  title={Part-Aware Self-Supervised Pre-Training for Person Re-Identification},
  author={Zhu, Kuan and Guo, Haiyun and Yan, Tianyi and Zhu, Yousong and Wang, Jinqiao and Tang, Ming},
  journal={arXiv preprint arXiv:2203.03931},
  year={2022}
}
```

## Contact

If you have any question, please feel free to contact us. E-mail: [kuan.zhu@nlpr.ia.ac.cn](kuan.zhu@nlpr.ia.ac.cn).
