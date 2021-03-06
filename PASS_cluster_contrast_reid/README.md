# Cluster Contrast for Unsupervised Person Re-Identification
We modify the code from [TransReID-SSL](https://github.com/damo-cv/TransReID-SSL) and [cluster-contrast-reid](https://github.com/alibaba/cluster-contrast-reid). You can refer to the original repo for more details.

### Installation

```shell
python setup.py develop
```

### Prepare Pre-trained Models 
Please download the pre-trained models and put them into your custom file folder.

Pre-trained model on MSMT17 for Market1501 [model](https://drive.google.com/file/d/1rXr-uV5I5osgu6lhW_UfeguOvAW0nXgx/view?usp=sharing).

Pre-trained model on Market1501 for MSMT17 [model](https://drive.google.com/file/d/1QQXU8x4EuxCMJ4hPi-NkAvNeenNz7AJy/view?usp=sharing).
### Training

You can use 2 or 4 GPUs for training. For more parameter configuration, please check **`market_usl.sh`**, **`market_uda.sh`**, **`msmt_usl.sh`** and **`msmt_uda.sh`**.

- Please set **`-pp`** as the file path of the pre-trained model. For UDA ReID, the pre-trained model should be fine-tuned on the source dataset at first.
- We observe high performance can be achieved on MSMT with 2 GPUs training.

## Citation

If you find this code useful for your research, please cite the paper
```
@article{dai2021cluster,
  title={Cluster Contrast for Unsupervised Person Re-Identification},
  author={Dai, Zuozhuo and Wang, Guangyuan and Zhu, Siyu and Yuan, Weihao and Tan, Ping},
  journal={arXiv preprint arXiv:2103.11568},
  year={2021}
}
```
