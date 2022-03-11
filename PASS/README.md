# Part-Aware Self-Supervised Pre-training (PASS)
We modify the code from [TransReID-SSL](https://github.com/damo-cv/TransReID-SSL) and [DINO](https://github.com/facebookresearch/dino).

## Training
Please set `--data_path` and `output_dir` in the shell files. 


- Training ViT-S
```bash
python -W ignore -m torch.distributed.launch --nproc_per_node=8 main_pass.py \
--arch vit_small \
--data_path /userhome/zhukuan/data/LUPerson_img_full \
--output_dir ./log/pass/vit_small_full_lup \
--height 256 --width 128 \
--crop_height 128 --crop_width 64 \
--epochs 100 \
--local_crops_number 9 \
--local_crops_scale 0.1 0.8 \
--batch_size_per_gpu 128
```

- Training ViT-B
```bash
python -W ignore -m torch.distributed.launch --nproc_per_node=8 main_pass.py \
--arch vit_base \
--data_path /userhome/zhukuan/data/LUPerson_img_full \
--output_dir ./log/pass/vit_base_full_lup \
--height 256 --width 128 \
--crop_height 128 --crop_width 64 \
--epochs 100 \
--local_crops_number 9 \
--local_crops_scale 0.1 0.8 \
--batch_size_per_gpu 64

```

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
