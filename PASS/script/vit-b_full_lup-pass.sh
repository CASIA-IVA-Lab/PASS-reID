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