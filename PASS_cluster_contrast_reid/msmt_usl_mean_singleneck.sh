# VIT-S
CUDA_VISIBLE_DEVICES=2,3 python examples/cluster_contrast_train_usl.py -b 256 -a vit_small -d msmt17 --data-dir '/userhome/zhukuan/data/' --iters 200 --eps 0.7 --self-norm --use-hard --hw-ratio 2 --num-instances 8 -pp "/userhome/zhukuan/PASS-reID/pre_trained_model/pass_vit_small_full.pth" --logs-dir ./log/cluster_contrast_reid/msmt17/pass_vit_small_full_lup_mean_singleneck --eval-step 50 --feat-fusion 'mean'

