#Single GPU
python train.py --config_file configs/msmt17/vit_base.yml MODEL.PRETRAIN_PATH "/userhome/zhukuan/PASS-reID/pre_trained_model/pass_vit_base_full.pth" OUTPUT_DIR './logs/msmt17/pass_vit_base_full_cat' SOLVER.SEED 42 MODEL.DEVICE_ID '("2")'


