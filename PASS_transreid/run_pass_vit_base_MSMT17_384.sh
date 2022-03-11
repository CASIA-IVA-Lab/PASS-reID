#Single GPU
python train.py --config_file configs/msmt17/vit_base.yml MODEL.PRETRAIN_PATH "/userhome/zhukuan/PASS-reID/pre_trained_model/pass_vit_base_full.pth" INPUT.SIZE_TRAIN [384,128] INPUT.SIZE_TEST [384,128] OUTPUT_DIR './logs/msmt17/pass_vit_base_full_cat_384_42' SOLVER.SEED 42 MODEL.DEVICE_ID '("3")'


