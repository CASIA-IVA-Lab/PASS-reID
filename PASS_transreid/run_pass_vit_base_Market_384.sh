#Single GPU
python train.py --config_file configs/market/vit_base.yml MODEL.PRETRAIN_PATH "/userhome/zhukuan/PASS-reID/pre_trained_model/pass_vit_base_full.pth" INPUT.SIZE_TRAIN [384,128] INPUT.SIZE_TEST [384,128] OUTPUT_DIR './logs/market/pass_vit_base_full_cat384'  MODEL.DEVICE_ID '("0")'


